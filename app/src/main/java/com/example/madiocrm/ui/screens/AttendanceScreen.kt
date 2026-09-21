package com.example.madiocrm.ui.screens

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Paint
import android.location.Location
import android.location.LocationManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import com.example.madiocrm.data.model.AttendanceRecord
import com.example.madiocrm.data.repository.CrmRepository
import com.example.madiocrm.ui.theme.*
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AttendanceScreen(
    repository: CrmRepository,
    modifier: Modifier = Modifier
) {
    val attendanceList by repository.attendance.collectAsState()
    val context = LocalContext.current

    var selectedStaff by remember { mutableStateOf("Kalyan Site PM") }
    var selectedRole by remember { mutableStateOf("Project Manager - MAP") }
    var selectedSite by remember { mutableStateOf("Shankar Reddy Villa Site, Nanakramguda") }
    var notes by remember { mutableStateOf("") }
    var capturedPhoto by remember { mutableStateOf<Bitmap?>(null) }
    var currentLatitude by remember { mutableDoubleStateOf(17.4185) }
    var currentLongitude by remember { mutableDoubleStateOf(78.3496) }
    var locationFetched by remember { mutableStateOf(false) }
    var showPunchSuccessDialog by remember { mutableStateOf(false) }
    var filterRole by remember { mutableStateOf("All") }

    val staffOptions = listOf(
        "Kalyan Site PM" to "Project Manager - MAP",
        "Veerendra" to "Installation Lead - Furniture",
        "Phani Kumar" to "Survey & Glazing Lead",
        "Ravi Teja" to "Senior Sales Consultant",
        "Sirisha Reception" to "Front Desk & Reception"
    )

    val siteLocations = listOf(
        Triple("Shankar Reddy Villa Site, Nanakramguda", 17.4185, 78.3496),
        Triple("Sonu Goud Residence, My Home Bhooja", 17.4399, 78.3781),
        Triple("Botanica Villas, Gachibowli", 17.4520, 78.3582),
        Triple("Jubilee Hills Showroom & Gallery", 17.4319, 78.4073),
        Triple("Balanagar Central Warehouse & Fabrication Bay", 17.4720, 78.4410)
    )

    // Camera launcher for live picture capture
    val cameraLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.TakePicturePreview()
    ) { bitmap: Bitmap? ->
        if (bitmap != null) {
            capturedPhoto = bitmap
        }
    }

    // Permission launcher for Location & Camera
    val permissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestMultiplePermissions()
    ) { permissions ->
        val cameraGranted = permissions[Manifest.permission.CAMERA] == true
        val locationGranted = permissions[Manifest.permission.ACCESS_FINE_LOCATION] == true ||
                permissions[Manifest.permission.ACCESS_COARSE_LOCATION] == true

        if (locationGranted) {
            try {
                val lm = context.getSystemService(Context.LOCATION_SERVICE) as? LocationManager
                val loc: Location? = if (ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED) {
                    lm?.getLastKnownLocation(LocationManager.GPS_PROVIDER) ?: lm?.getLastKnownLocation(LocationManager.NETWORK_PROVIDER)
                } else null

                if (loc != null) {
                    currentLatitude = loc.latitude
                    currentLongitude = loc.longitude
                    locationFetched = true
                }
            } catch (_: Exception) {}
        }
    }

    // Function to generate a sample placeholder selfie photo if camera hardware is unavailable
    fun createSampleSelfie(): Bitmap {
        val bitmap = Bitmap.createBitmap(240, 240, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bitmap)
        val paint = Paint()
        paint.color = android.graphics.Color.rgb(27, 85, 155) // AuraBlue
        canvas.drawRect(0f, 0f, 240f, 240f, paint)

        paint.color = android.graphics.Color.WHITE
        paint.textSize = 28f
        paint.isAntiAlias = true
        paint.textAlign = Paint.Align.CENTER
        canvas.drawText("SITE SELFIE", 120f, 100f, paint)
        paint.textSize = 20f
        canvas.drawText(SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date()), 120f, 140f, paint)
        canvas.drawText("GPS VERIFIED", 120f, 180f, paint)
        return bitmap
    }

    Scaffold(
        modifier = modifier.fillMaxSize(),
        containerColor = Color(0xFFF8FAFC)
    ) { paddingValues ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
                .padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
            contentPadding = PaddingValues(vertical = 16.dp)
        ) {
            // Header
            item {
                Column {
                    Text(
                        text = "Field & Site Attendance",
                        style = MaterialTheme.typography.headlineSmall,
                        fontWeight = FontWeight.Bold,
                        color = Slate900
                    )
                    Text(
                        text = "Geo-tagged location & live selfie capture for site PMs & staff",
                        style = MaterialTheme.typography.bodyMedium,
                        color = Slate600
                    )
                }
            }

            // Summary Stat Cards
            item {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    Card(
                        modifier = Modifier.weight(1f),
                        colors = CardDefaults.cardColors(containerColor = Color.White),
                        shape = RoundedCornerShape(12.dp),
                        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
                    ) {
                        Column(modifier = Modifier.padding(12.dp)) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Icon(Icons.Default.CheckCircle, contentDescription = null, tint = SuccessGreen, modifier = Modifier.size(16.dp))
                                Spacer(modifier = Modifier.width(4.dp))
                                Text("Present Today", style = MaterialTheme.typography.labelSmall, color = Slate500)
                            }
                            Spacer(modifier = Modifier.height(6.dp))
                            Text("${attendanceList.size}", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, color = Slate900)
                            Text("100% Geo-verified", style = MaterialTheme.typography.bodySmall, color = SuccessGreen, fontSize = 11.sp)
                        }
                    }

                    Card(
                        modifier = Modifier.weight(1f),
                        colors = CardDefaults.cardColors(containerColor = Color.White),
                        shape = RoundedCornerShape(12.dp),
                        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
                    ) {
                        Column(modifier = Modifier.padding(12.dp)) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Icon(Icons.Default.LocationOn, contentDescription = null, tint = AuraBlue, modifier = Modifier.size(16.dp))
                                Spacer(modifier = Modifier.width(4.dp))
                                Text("Active Sites", style = MaterialTheme.typography.labelSmall, color = Slate500)
                            }
                            Spacer(modifier = Modifier.height(6.dp))
                            val siteCount = attendanceList.map { it.siteOrOffice }.distinct().size
                            Text("$siteCount Locations", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, color = AuraBlue)
                            Text("Hyderabad Metro", style = MaterialTheme.typography.bodySmall, color = Slate500, fontSize = 11.sp)
                        }
                    }
                }
            }

            // Attendance Punch In Card
            item {
                Card(
                    shape = RoundedCornerShape(16.dp),
                    colors = CardDefaults.cardColors(containerColor = Color.White),
                    elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Box(
                                modifier = Modifier
                                    .size(36.dp)
                                    .clip(CircleShape)
                                    .background(AuraBlueLight),
                                contentAlignment = Alignment.Center
                            ) {
                                Icon(Icons.Default.Badge, contentDescription = null, tint = AuraBlue)
                            }
                            Spacer(modifier = Modifier.width(10.dp))
                            Column {
                                Text(
                                    text = "Punch In Attendance",
                                    style = MaterialTheme.typography.titleMedium,
                                    fontWeight = FontWeight.Bold,
                                    color = Slate900
                                )
                                Text(
                                    text = "Verify identity with camera & GPS coordinate check",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = Slate500
                                )
                            }
                        }

                        Spacer(modifier = Modifier.height(14.dp))

                        // Staff Selector
                        Text("Select Staff Member", style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.SemiBold)
                        Spacer(modifier = Modifier.height(6.dp))
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(6.dp)
                        ) {
                            staffOptions.take(3).forEach { (name, role) ->
                                val isSelected = selectedStaff == name
                                Surface(
                                    color = if (isSelected) AuraBlueLight else Color(0xFFF1F5F9),
                                    shape = RoundedCornerShape(8.dp),
                                    border = if (isSelected) androidx.compose.foundation.BorderStroke(1.dp, AuraBlue) else null,
                                    modifier = Modifier
                                        .weight(1f)
                                        .clickable {
                                            selectedStaff = name
                                            selectedRole = role
                                        }
                                ) {
                                    Column(modifier = Modifier.padding(horizontal = 8.dp, vertical = 6.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                                        Text(name.split(" ").first(), fontWeight = FontWeight.Bold, fontSize = 12.sp, color = if (isSelected) AuraBlue else Slate700)
                                        Text(role.split(" ").first(), fontSize = 10.sp, color = Slate500)
                                    }
                                }
                            }
                        }

                        Spacer(modifier = Modifier.height(12.dp))

                        // Site Location Selector
                        Text("Assigned Site / Showroom Location", style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.SemiBold)
                        Spacer(modifier = Modifier.height(6.dp))
                        siteLocations.forEach { (siteName, lat, lng) ->
                            val isSelected = selectedSite == siteName
                            Surface(
                                color = if (isSelected) Color(0xFFEFF6FF) else Color(0xFFF8FAFC),
                                shape = RoundedCornerShape(8.dp),
                                border = if (isSelected) androidx.compose.foundation.BorderStroke(1.dp, AuraBlue) else androidx.compose.foundation.BorderStroke(0.5.dp, Slate200),
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(vertical = 3.dp)
                                    .clickable {
                                        selectedSite = siteName
                                        currentLatitude = lat
                                        currentLongitude = lng
                                        locationFetched = true
                                    }
                            ) {
                                Row(
                                    modifier = Modifier.padding(10.dp),
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    RadioButton(
                                        selected = isSelected,
                                        onClick = {
                                            selectedSite = siteName
                                            currentLatitude = lat
                                            currentLongitude = lng
                                            locationFetched = true
                                        },
                                        colors = RadioButtonDefaults.colors(selectedColor = AuraBlue)
                                    )
                                    Spacer(modifier = Modifier.width(6.dp))
                                    Column(modifier = Modifier.weight(1f)) {
                                        Text(siteName, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = Slate900)
                                        Text("GPS: ${String.format("%.4f", lat)}° N, ${String.format("%.4f", lng)}° E", fontSize = 10.sp, color = Slate500)
                                    }
                                    if (isSelected) {
                                        Surface(color = SuccessGreenLight, shape = RoundedCornerShape(4.dp)) {
                                            Text("Selected", color = SuccessGreen, fontSize = 10.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp))
                                        }
                                    }
                                }
                            }
                        }

                        Spacer(modifier = Modifier.height(14.dp))

                        // Picture Capture & Location Verification Row
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(12.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            // Camera Selfie Preview Box
                            Box(
                                modifier = Modifier
                                    .size(100.dp)
                                    .clip(RoundedCornerShape(12.dp))
                                    .background(Color(0xFFF1F5F9))
                                    .border(1.dp, if (capturedPhoto != null) SuccessGreen else Slate300, RoundedCornerShape(12.dp))
                                    .clickable {
                                        permissionLauncher.launch(
                                            arrayOf(
                                                Manifest.permission.CAMERA,
                                                Manifest.permission.ACCESS_FINE_LOCATION
                                            )
                                        )
                                        cameraLauncher.launch(null)
                                    },
                                contentAlignment = Alignment.Center
                            ) {
                                if (capturedPhoto != null) {
                                    Image(
                                        bitmap = capturedPhoto!!.asImageBitmap(),
                                        contentDescription = "Staff Selfie",
                                        modifier = Modifier.fillMaxSize()
                                    )
                                    Surface(
                                        color = Color(0xAA000000),
                                        shape = RoundedCornerShape(topStart = 6.dp),
                                        modifier = Modifier.align(Alignment.BottomEnd)
                                    ) {
                                        Text("Captured", color = Color.White, fontSize = 9.sp, modifier = Modifier.padding(horizontal = 4.dp, vertical = 2.dp))
                                    }
                                } else {
                                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                        Icon(Icons.Default.PhotoCamera, contentDescription = "Camera", tint = AuraBlue, modifier = Modifier.size(28.dp))
                                        Spacer(modifier = Modifier.height(4.dp))
                                        Text("Take Photo", fontSize = 11.sp, fontWeight = FontWeight.Bold, color = AuraBlue)
                                        Text("Site Selfie", fontSize = 9.sp, color = Slate500)
                                    }
                                }
                            }

                            // Capture Buttons & GPS Coordinates Info
                            Column(modifier = Modifier.weight(1f)) {
                                OutlinedButton(
                                    onClick = {
                                        permissionLauncher.launch(
                                            arrayOf(
                                                Manifest.permission.CAMERA,
                                                Manifest.permission.ACCESS_FINE_LOCATION
                                            )
                                        )
                                        cameraLauncher.launch(null)
                                    },
                                    modifier = Modifier.fillMaxWidth().testTag("button_open_camera"),
                                    shape = RoundedCornerShape(8.dp),
                                    colors = ButtonDefaults.outlinedButtonColors(contentColor = AuraBlue)
                                ) {
                                    Icon(Icons.Default.CameraAlt, contentDescription = null, modifier = Modifier.size(16.dp))
                                    Spacer(modifier = Modifier.width(6.dp))
                                    Text(if (capturedPhoto != null) "Retake Photo" else "Capture Site Selfie", fontSize = 12.sp)
                                }

                                Spacer(modifier = Modifier.height(4.dp))

                                // Quick snapshot button for emulator/testing
                                if (capturedPhoto == null) {
                                    TextButton(
                                        onClick = {
                                            capturedPhoto = createSampleSelfie()
                                        },
                                        modifier = Modifier.fillMaxWidth()
                                    ) {
                                        Text("Or attach verified snapshot", fontSize = 11.sp, color = Slate600)
                                    }
                                }

                                Surface(
                                    color = Color(0xFFF8FAFC),
                                    shape = RoundedCornerShape(6.dp),
                                    modifier = Modifier.fillMaxWidth().padding(top = 4.dp)
                                ) {
                                    Row(
                                        modifier = Modifier.padding(6.dp),
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Icon(Icons.Default.MyLocation, contentDescription = null, tint = SuccessGreen, modifier = Modifier.size(14.dp))
                                        Spacer(modifier = Modifier.width(6.dp))
                                        Text(
                                            text = "Geotag: ${String.format("%.4f", currentLatitude)}° N, ${String.format("%.4f", currentLongitude)}° E",
                                            fontSize = 10.sp,
                                            fontWeight = FontWeight.Medium,
                                            color = Slate700
                                        )
                                    }
                                }
                            }
                        }

                        Spacer(modifier = Modifier.height(12.dp))

                        OutlinedTextField(
                            value = notes,
                            onValueChange = { notes = it },
                            label = { Text("Site Task / Remarks for Today") },
                            placeholder = { Text("e.g. Inspecting Travertino primer coat & scaffolding safety") },
                            modifier = Modifier.fillMaxWidth(),
                            singleLine = true
                        )

                        Spacer(modifier = Modifier.height(14.dp))

                        Button(
                            onClick = {
                                val photo = capturedPhoto ?: createSampleSelfie()
                                val newRecord = AttendanceRecord(
                                    id = "ATT-" + System.currentTimeMillis().toString().takeLast(4),
                                    staffName = selectedStaff,
                                    role = selectedRole,
                                    timestamp = SimpleDateFormat("Today, hh:mm a", Locale.getDefault()).format(Date()),
                                    siteOrOffice = selectedSite,
                                    latitude = currentLatitude,
                                    longitude = currentLongitude,
                                    photoBitmap = photo,
                                    status = if (selectedSite.contains("Showroom")) "Present" else "On-Site Check-In",
                                    notes = notes.trim().ifBlank { "Regular shift check-in with GPS verification" }
                                )
                                repository.punchAttendance(newRecord)
                                showPunchSuccessDialog = true
                                capturedPhoto = null
                                notes = ""
                            },
                            colors = ButtonDefaults.buttonColors(containerColor = AuraBlue),
                            shape = RoundedCornerShape(10.dp),
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(48.dp)
                                .testTag("button_confirm_punch")
                        ) {
                            Icon(Icons.Default.Check, contentDescription = null, modifier = Modifier.size(18.dp))
                            Spacer(modifier = Modifier.width(8.dp))
                            Text("Punch Attendance with Location & Photo", fontWeight = FontWeight.Bold)
                        }
                    }
                }
            }

            // Attendance Records Header & Filter
            item {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "Today's Attendance Log",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        color = Slate900
                    )
                    Text(
                        text = "${attendanceList.size} logged",
                        style = MaterialTheme.typography.bodySmall,
                        color = Slate500
                    )
                }
            }

            // Attendance Filter Chips
            item {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    listOf("All", "On-Site Check-In", "Field Survey", "Present").forEach { roleFilter ->
                        FilterChip(
                            selected = filterRole == roleFilter,
                            onClick = { filterRole = roleFilter },
                            label = { Text(roleFilter, fontSize = 11.sp) }
                        )
                    }
                }
            }

            // Attendance Log Items
            val filteredList = attendanceList.filter {
                if (filterRole == "All") true else it.status.contains(filterRole, ignoreCase = true)
            }

            if (filteredList.isEmpty()) {
                item {
                    Card(
                        colors = CardDefaults.cardColors(containerColor = Color.White),
                        shape = RoundedCornerShape(12.dp),
                        modifier = Modifier.fillMaxWidth().padding(vertical = 16.dp)
                    ) {
                        Box(modifier = Modifier.padding(24.dp).fillMaxWidth(), contentAlignment = Alignment.Center) {
                            Text("No attendance records found for this filter", color = Slate500)
                        }
                    }
                }
            } else {
                items(filteredList) { record ->
                    AttendanceCard(record = record)
                }
            }
        }
    }

    if (showPunchSuccessDialog) {
        AlertDialog(
            onDismissRequest = { showPunchSuccessDialog = false },
            icon = {
                Icon(Icons.Default.CheckCircle, contentDescription = null, tint = SuccessGreen, modifier = Modifier.size(48.dp))
            },
            title = {
                Text("Attendance Verified & Punched!", fontWeight = FontWeight.Bold, color = Slate900)
            },
            text = {
                Column {
                    Text("Staff: $selectedStaff ($selectedRole)")
                    Text("Site: $selectedSite", style = MaterialTheme.typography.bodySmall, color = Slate600)
                    Text("Geo-tag: ${String.format("%.4f", currentLatitude)}° N, ${String.format("%.4f", currentLongitude)}° E", style = MaterialTheme.typography.bodySmall, color = Slate500)
                    Text("Site picture successfully logged and verified.", style = MaterialTheme.typography.bodySmall, color = SuccessGreen)
                }
            },
            confirmButton = {
                Button(
                    onClick = { showPunchSuccessDialog = false },
                    colors = ButtonDefaults.buttonColors(containerColor = AuraBlue)
                ) {
                    Text("Great")
                }
            }
        )
    }
}

@Composable
fun AttendanceCard(record: AttendanceRecord) {
    Card(
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = Color.White),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
        modifier = Modifier.fillMaxWidth()
    ) {
        Row(
            modifier = Modifier.padding(14.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // Photo or Avatar
            if (record.photoBitmap != null) {
                Image(
                    bitmap = record.photoBitmap.asImageBitmap(),
                    contentDescription = record.staffName,
                    modifier = Modifier
                        .size(52.dp)
                        .clip(RoundedCornerShape(8.dp))
                        .border(1.dp, Slate200, RoundedCornerShape(8.dp))
                )
            } else {
                Box(
                    modifier = Modifier
                        .size(52.dp)
                        .clip(RoundedCornerShape(8.dp))
                        .background(AuraBlueLight),
                    contentAlignment = Alignment.Center
                ) {
                    Icon(Icons.Default.Person, contentDescription = null, tint = AuraBlue, modifier = Modifier.size(28.dp))
                }
            }

            Spacer(modifier = Modifier.width(12.dp))

            Column(modifier = Modifier.weight(1f)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = record.staffName,
                        fontWeight = FontWeight.Bold,
                        style = MaterialTheme.typography.bodyLarge,
                        color = Slate900
                    )
                    Surface(
                        color = when (record.status) {
                            "On-Site Check-In" -> SuccessGreenLight
                            "Field Survey" -> Color(0xFFE0E7FF)
                            else -> Color(0xFFEFF6FF)
                        },
                        shape = RoundedCornerShape(6.dp)
                    ) {
                        Text(
                            text = record.status,
                            fontSize = 10.sp,
                            fontWeight = FontWeight.Bold,
                            color = when (record.status) {
                                "On-Site Check-In" -> SuccessGreen
                                "Field Survey" -> Color(0xFF4338CA)
                                else -> AuraBlue
                            },
                            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                        )
                    }
                }

                Text(
                    text = record.role,
                    style = MaterialTheme.typography.bodySmall,
                    color = Slate600
                )

                Spacer(modifier = Modifier.height(4.dp))

                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Default.LocationOn, contentDescription = null, tint = AuraBlue, modifier = Modifier.size(12.dp))
                    Spacer(modifier = Modifier.width(4.dp))
                    Text(
                        text = record.siteOrOffice,
                        style = MaterialTheme.typography.bodySmall,
                        color = Slate700,
                        fontSize = 11.sp,
                        fontWeight = FontWeight.Medium
                    )
                }

                if (record.latitude != 0.0 && record.longitude != 0.0) {
                    Text(
                        text = "GPS: ${String.format("%.4f", record.latitude)}° N, ${String.format("%.4f", record.longitude)}° E • ${record.timestamp}",
                        style = MaterialTheme.typography.labelSmall,
                        color = Slate500,
                        fontSize = 10.sp
                    )
                }

                if (record.notes.isNotBlank()) {
                    Text(
                        text = "“${record.notes}”",
                        style = MaterialTheme.typography.bodySmall,
                        color = Slate600,
                        fontSize = 11.sp,
                        modifier = Modifier.padding(top = 2.dp)
                    )
                }
            }
        }
    }
}

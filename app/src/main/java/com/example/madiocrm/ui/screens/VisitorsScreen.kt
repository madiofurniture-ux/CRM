package com.example.madiocrm.ui.screens

import android.content.Intent
import android.net.Uri
import android.widget.Toast
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.madiocrm.data.model.Division
import com.example.madiocrm.data.model.Visitor
import com.example.madiocrm.data.repository.CrmRepository
import com.example.madiocrm.ui.components.AddVisitorDialog
import com.example.madiocrm.ui.components.DivisionBadge
import com.example.madiocrm.ui.theme.*

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun VisitorsScreen(
    repository: CrmRepository,
    onNavigateToLeads: () -> Unit = {},
    modifier: Modifier = Modifier
) {
    val visitors by repository.visitors.collectAsState()
    val context = LocalContext.current

    var searchQuery by remember { mutableStateOf("") }
    var selectedDivision by remember { mutableStateOf(Division.ALL) }
    var selectedStatusFilter by remember { mutableStateOf("ALL") } // ALL, NEW, CONVERTED
    var showAddVisitorDialog by remember { mutableStateOf(false) }

    val filteredVisitors = remember(visitors, searchQuery, selectedDivision, selectedStatusFilter) {
        visitors.filter { visitor ->
            val matchesDivision = selectedDivision == Division.ALL || visitor.division == selectedDivision
            val isConverted = visitor.status == "Converted to Lead"
            val matchesStatus = when (selectedStatusFilter) {
                "NEW" -> !isConverted
                "CONVERTED" -> isConverted
                else -> true
            }
            val matchesSearch = searchQuery.isBlank() ||
                    visitor.name.contains(searchQuery, ignoreCase = true) ||
                    visitor.phone.contains(searchQuery) ||
                    visitor.interestedIn.contains(searchQuery, ignoreCase = true) ||
                    visitor.attendedBy.contains(searchQuery, ignoreCase = true) ||
                    visitor.notes.contains(searchQuery, ignoreCase = true)
            matchesDivision && matchesStatus && matchesSearch
        }
    }

    val totalVisitors = visitors.size
    val convertedCount = visitors.count { it.status == "Converted to Lead" }
    val newWalkinsCount = totalVisitors - convertedCount
    val conversionRate = if (totalVisitors > 0) ((convertedCount.toFloat() / totalVisitors) * 100).toInt() else 0

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text(
                            "Showroom Visitors",
                            fontWeight = FontWeight.Bold,
                            style = MaterialTheme.typography.titleLarge
                        )
                        Text(
                            "$totalVisitors Logged Walk-ins • $convertedCount Converted to Leads",
                            style = MaterialTheme.typography.bodySmall,
                            color = Slate500
                        )
                    }
                },
                actions = {
                    IconButton(
                        onClick = { showAddVisitorDialog = true },
                        modifier = Modifier.testTag("action_log_visitor")
                    ) {
                        Icon(
                            Icons.Default.PersonAdd,
                            contentDescription = "Log Visitor",
                            tint = AuraBlue
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = Color.White)
            )
        },
        floatingActionButton = {
            ExtendedFloatingActionButton(
                onClick = { showAddVisitorDialog = true },
                containerColor = AuraBlue,
                contentColor = Color.White,
                shape = RoundedCornerShape(16.dp),
                icon = { Icon(Icons.Default.PersonAdd, contentDescription = null) },
                text = { Text("Log Visitor", fontWeight = FontWeight.Bold) },
                modifier = Modifier
                    .testTag("fab_add_visitor")
            )
        },
        modifier = modifier
    ) { innerPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .background(Slate50)
                .padding(innerPadding)
        ) {
            // Metrics Summary
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 8.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Card(
                    colors = CardDefaults.cardColors(containerColor = Color.White),
                    shape = RoundedCornerShape(12.dp),
                    elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
                    modifier = Modifier.weight(1f)
                ) {
                    Column(modifier = Modifier.padding(10.dp)) {
                        Text("Total Walk-ins", style = MaterialTheme.typography.bodySmall, color = Slate500, fontSize = 11.sp)
                        Text("$totalVisitors", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = Slate900)
                    }
                }

                Card(
                    colors = CardDefaults.cardColors(containerColor = Color.White),
                    shape = RoundedCornerShape(12.dp),
                    elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
                    modifier = Modifier.weight(1f)
                ) {
                    Column(modifier = Modifier.padding(10.dp)) {
                        Text("New Inquiries", style = MaterialTheme.typography.bodySmall, color = Slate500, fontSize = 11.sp)
                        Text("$newWalkinsCount", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = AuraBlue)
                    }
                }

                Card(
                    colors = CardDefaults.cardColors(containerColor = Color.White),
                    shape = RoundedCornerShape(12.dp),
                    elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
                    modifier = Modifier.weight(1f)
                ) {
                    Column(modifier = Modifier.padding(10.dp)) {
                        Text("Conversion", style = MaterialTheme.typography.bodySmall, color = Slate500, fontSize = 11.sp)
                        Text("$conversionRate%", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = SuccessGreen)
                    }
                }
            }

            // Search Bar
            OutlinedTextField(
                value = searchQuery,
                onValueChange = { searchQuery = it },
                placeholder = { Text("Search by name, phone, interests, host...", color = Slate400, fontSize = 13.sp) },
                leadingIcon = { Icon(Icons.Default.Search, contentDescription = null, tint = Slate400) },
                trailingIcon = {
                    if (searchQuery.isNotEmpty()) {
                        IconButton(onClick = { searchQuery = "" }) {
                            Icon(Icons.Default.Close, contentDescription = "Clear", tint = Slate400)
                        }
                    }
                },
                shape = RoundedCornerShape(12.dp),
                colors = OutlinedTextFieldDefaults.colors(
                    focusedContainerColor = Color.White,
                    unfocusedContainerColor = Color.White,
                    focusedBorderColor = AuraBlue,
                    unfocusedBorderColor = Slate200
                ),
                singleLine = true,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 4.dp)
                    .testTag("input_search_visitors")
            )

            // Division Filter Chips
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .horizontalScroll(rememberScrollState())
                    .padding(horizontal = 16.dp, vertical = 6.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Division.values().forEach { div ->
                    FilterChip(
                        selected = selectedDivision == div,
                        onClick = { selectedDivision = div },
                        label = {
                            Text(
                                div.displayName,
                                fontSize = 12.sp
                            )
                        },
                        colors = FilterChipDefaults.filterChipColors(
                            selectedContainerColor = AuraBlue,
                            selectedLabelColor = Color.White
                        )
                    )
                }
            }

            // Status Filter Chips
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 2.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                listOf(
                    "ALL" to "All Visitors (${visitors.size})",
                    "NEW" to "Active Walk-ins ($newWalkinsCount)",
                    "CONVERTED" to "Converted ($convertedCount)"
                ).forEach { (statusKey, label) ->
                    FilterChip(
                        selected = selectedStatusFilter == statusKey,
                        onClick = { selectedStatusFilter = statusKey },
                        label = { Text(label, fontSize = 11.sp) },
                        colors = FilterChipDefaults.filterChipColors(
                            selectedContainerColor = Slate700,
                            selectedLabelColor = Color.White
                        )
                    )
                }
            }

            Spacer(modifier = Modifier.height(4.dp))

            // Visitors List
            if (filteredVisitors.isEmpty()) {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(32.dp),
                    contentAlignment = Alignment.Center
                ) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Icon(
                            Icons.Default.Storefront,
                            contentDescription = null,
                            tint = Slate300,
                            modifier = Modifier.size(64.dp)
                        )
                        Spacer(modifier = Modifier.height(12.dp))
                        Text(
                            "No visitors match your criteria",
                            style = MaterialTheme.typography.titleMedium,
                            color = Slate600
                        )
                        Spacer(modifier = Modifier.height(6.dp))
                        Text(
                            "Log showroom walk-ins or adjust your search filter",
                            style = MaterialTheme.typography.bodySmall,
                            color = Slate400
                        )
                        Spacer(modifier = Modifier.height(12.dp))
                        Button(
                            onClick = { showAddVisitorDialog = true },
                            colors = ButtonDefaults.buttonColors(containerColor = AuraBlue),
                            shape = RoundedCornerShape(10.dp)
                        ) {
                            Icon(Icons.Default.PersonAdd, contentDescription = null, modifier = Modifier.size(16.dp))
                            Spacer(modifier = Modifier.width(6.dp))
                            Text("Log Showroom Visitor")
                        }
                    }
                }
            } else {
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 6.dp, bottom = 80.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    items(filteredVisitors, key = { it.id }) { visitor ->
                        val isConverted = visitor.status == "Converted to Lead"
                        Card(
                            colors = CardDefaults.cardColors(containerColor = Color.White),
                            shape = RoundedCornerShape(16.dp),
                            elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
                            modifier = Modifier
                                .fillMaxWidth()
                                .testTag("visitor_card_${visitor.id}")
                        ) {
                            Column(modifier = Modifier.padding(16.dp)) {
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.SpaceBetween,
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Column(modifier = Modifier.weight(1f)) {
                                        Row(verticalAlignment = Alignment.CenterVertically) {
                                            Text(
                                                text = visitor.name,
                                                style = MaterialTheme.typography.titleMedium,
                                                fontWeight = FontWeight.Bold,
                                                color = Slate900
                                            )
                                            Spacer(modifier = Modifier.width(8.dp))
                                            DivisionBadge(visitor.division)
                                        }
                                        Text(
                                            text = "${visitor.phone} • Check-in: ${visitor.checkInTime}",
                                            style = MaterialTheme.typography.bodySmall,
                                            color = Slate500
                                        )
                                    }

                                    Surface(
                                        color = if (isConverted) SuccessGreenLight else Color(0xFFEFF6FF),
                                        shape = RoundedCornerShape(8.dp)
                                    ) {
                                        Text(
                                            text = visitor.status,
                                            fontSize = 11.sp,
                                            fontWeight = FontWeight.Bold,
                                            color = if (isConverted) SuccessGreen else AuraBlue,
                                            modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                                        )
                                    }
                                }

                                Spacer(modifier = Modifier.height(10.dp))

                                Surface(
                                    color = Color(0xFFF8FAFC),
                                    shape = RoundedCornerShape(10.dp),
                                    modifier = Modifier.fillMaxWidth()
                                ) {
                                    Column(modifier = Modifier.padding(10.dp)) {
                                        Row(verticalAlignment = Alignment.CenterVertically) {
                                            Icon(
                                                Icons.Default.ShoppingBag,
                                                contentDescription = null,
                                                tint = AuraBlue,
                                                modifier = Modifier.size(14.dp)
                                            )
                                            Spacer(modifier = Modifier.width(6.dp))
                                            Text(
                                                "Interested In: ${visitor.interestedIn}",
                                                fontSize = 12.sp,
                                                fontWeight = FontWeight.SemiBold,
                                                color = Slate800
                                            )
                                        }
                                        if (visitor.notes.isNotBlank()) {
                                            Spacer(modifier = Modifier.height(4.dp))
                                            Text(
                                                "Notes: ${visitor.notes}",
                                                fontSize = 11.sp,
                                                color = Slate600
                                            )
                                        }
                                        Spacer(modifier = Modifier.height(4.dp))
                                        Text(
                                            "Attended by: ${visitor.attendedBy} • Purpose: ${visitor.purpose}",
                                            fontSize = 10.sp,
                                            color = Slate500
                                        )
                                    }
                                }

                                Spacer(modifier = Modifier.height(10.dp))

                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.SpaceBetween,
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                        FilledTonalIconButton(
                                            onClick = {
                                                val intent = Intent(Intent.ACTION_DIAL, Uri.parse("tel:${visitor.phone}"))
                                                context.startActivity(intent)
                                            },
                                            colors = IconButtonDefaults.filledTonalIconButtonColors(containerColor = Slate100),
                                            modifier = Modifier.size(36.dp)
                                        ) {
                                            Icon(Icons.Default.Phone, contentDescription = "Call", tint = AuraBlue, modifier = Modifier.size(18.dp))
                                        }

                                        FilledTonalIconButton(
                                            onClick = {
                                                val cleanPhone = visitor.phone.replace("+", "").replace(" ", "").replace("-", "")
                                                val uri = Uri.parse("https://api.whatsapp.com/send?phone=$cleanPhone&text=Hello%20${Uri.encode(visitor.name)},%20thank%20you%20for%20visiting%20MADIO%20Showroom!%20Regarding%20your%20interest%20in%20${Uri.encode(visitor.interestedIn)},%20how%20can%20we%20assist%20you?")
                                                val intent = Intent(Intent.ACTION_VIEW, uri)
                                                context.startActivity(intent)
                                            },
                                            colors = IconButtonDefaults.filledTonalIconButtonColors(containerColor = Color(0xFFE8F8F0)),
                                            modifier = Modifier.size(36.dp)
                                        ) {
                                            Icon(Icons.Default.Chat, contentDescription = "WhatsApp", tint = Color(0xFF25D366), modifier = Modifier.size(18.dp))
                                        }
                                    }

                                    if (!isConverted) {
                                        Button(
                                            onClick = {
                                                val newLead = repository.convertVisitorToLead(visitor)
                                                Toast.makeText(context, "Visitor converted to Lead ${newLead.id}!", Toast.LENGTH_SHORT).show()
                                            },
                                            colors = ButtonDefaults.buttonColors(containerColor = AuraBlue),
                                            shape = RoundedCornerShape(10.dp),
                                            contentPadding = PaddingValues(horizontal = 14.dp, vertical = 6.dp)
                                        ) {
                                            Icon(Icons.Default.PersonAdd, contentDescription = null, modifier = Modifier.size(16.dp))
                                            Spacer(modifier = Modifier.width(6.dp))
                                            Text("Convert to Lead", fontSize = 12.sp, fontWeight = FontWeight.Bold)
                                        }
                                    } else {
                                        Row(
                                            verticalAlignment = Alignment.CenterVertically,
                                            modifier = Modifier
                                                .clickable { onNavigateToLeads() }
                                                .padding(4.dp)
                                        ) {
                                            Text(
                                                text = "Linked Lead: ${visitor.convertedLeadId ?: ""}",
                                                fontSize = 12.sp,
                                                fontWeight = FontWeight.SemiBold,
                                                color = SuccessGreen
                                            )
                                            Spacer(modifier = Modifier.width(4.dp))
                                            Icon(
                                                Icons.Default.ChevronRight,
                                                contentDescription = "View Lead",
                                                tint = SuccessGreen,
                                                modifier = Modifier.size(16.dp)
                                            )
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    if (showAddVisitorDialog) {
        AddVisitorDialog(
            onDismiss = { showAddVisitorDialog = false },
            onSave = { newVisitor ->
                repository.addVisitor(newVisitor)
                showAddVisitorDialog = false
                Toast.makeText(context, "Visitor ${newVisitor.name} logged successfully!", Toast.LENGTH_SHORT).show()
            }
        )
    }
}

package com.example.madiocrm.ui.screens

import android.content.Intent
import android.net.Uri
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
import com.example.madiocrm.data.model.*
import com.example.madiocrm.data.repository.CrmRepository
import com.example.madiocrm.ui.components.*
import com.example.madiocrm.ui.theme.*

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LeadsScreen(
    repository: CrmRepository,
    onOpenAddLead: () -> Unit,
    onConvertToQuote: (Lead) -> Unit,
    onNavigateToProjects: () -> Unit = {},
    modifier: Modifier = Modifier
) {
    val leads by repository.leads.collectAsState()
    val visitors by repository.visitors.collectAsState()
    val surveys by repository.surveys.collectAsState()
    val quotes by repository.quotes.collectAsState()
    val sales by repository.sales.collectAsState()
    val projects by repository.projects.collectAsState()
    val wallets by repository.projectWallets.collectAsState()
    val context = LocalContext.current

    var mainTab by remember { mutableIntStateOf(0) } // 0: Leads, 1: Showroom Visitors, 2: Linked Pipeline Flow
    var searchQuery by remember { mutableStateOf("") }
    var selectedDivision by remember { mutableStateOf(Division.ALL) }
    var selectedStageFilter by remember { mutableStateOf<LeadStage?>(null) }

    // Dialog States
    var showAddVisitorDialog by remember { mutableStateOf(false) }
    var surveyTargetLead by remember { mutableStateOf<Lead?>(null) }
    var journeyTargetLead by remember { mutableStateOf<Lead?>(null) }
    var toastMessage by remember { mutableStateOf<String?>(null) }

    val filteredLeads = remember(leads, searchQuery, selectedDivision, selectedStageFilter) {
        leads.filter { lead ->
            val matchesDivision = selectedDivision == Division.ALL || lead.division == selectedDivision
            val matchesStage = selectedStageFilter == null || lead.stage == selectedStageFilter
            val matchesSearch = searchQuery.isBlank() ||
                    lead.name.contains(searchQuery, ignoreCase = true) ||
                    lead.phone.contains(searchQuery) ||
                    lead.remarks.contains(searchQuery, ignoreCase = true) ||
                    lead.source.contains(searchQuery, ignoreCase = true)
            matchesDivision && matchesStage && matchesSearch
        }
    }

    val filteredVisitors = remember(visitors, searchQuery, selectedDivision) {
        visitors.filter { visitor ->
            val matchesDivision = selectedDivision == Division.ALL || visitor.division == selectedDivision
            val matchesSearch = searchQuery.isBlank() ||
                    visitor.name.contains(searchQuery, ignoreCase = true) ||
                    visitor.phone.contains(searchQuery) ||
                    visitor.interestedIn.contains(searchQuery, ignoreCase = true) ||
                    visitor.notes.contains(searchQuery, ignoreCase = true)
            matchesDivision && matchesSearch
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text("Lead & Inquiry Management", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleLarge)
                        Text(
                            when (mainTab) {
                                0 -> "${filteredLeads.size} Active Client Leads"
                                1 -> "${filteredVisitors.size} Showroom Walk-ins & Inquiries"
                                else -> "Seamless End-to-End Pipeline Map"
                            },
                            style = MaterialTheme.typography.bodySmall,
                            color = Slate500
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = Color.White),
                actions = {
                    if (mainTab == 1) {
                        IconButton(
                            onClick = { showAddVisitorDialog = true },
                            modifier = Modifier.testTag("button_top_add_visitor")
                        ) {
                            Icon(Icons.Default.PersonAdd, contentDescription = "Log Visitor", tint = AuraBlue)
                        }
                    } else {
                        IconButton(
                            onClick = onOpenAddLead,
                            modifier = Modifier.testTag("add_lead_top_button")
                        ) {
                            Icon(Icons.Default.Add, contentDescription = "Add Lead", tint = AuraBlue)
                        }
                    }
                }
            )
        },
        floatingActionButton = {
            FloatingActionButton(
                onClick = {
                    if (mainTab == 1) {
                        showAddVisitorDialog = true
                    } else {
                        onOpenAddLead()
                    }
                },
                containerColor = AuraBlue,
                contentColor = Color.White,
                shape = CircleShape,
                modifier = Modifier
                    .padding(bottom = 60.dp)
                    .testTag("leads_fab_add")
            ) {
                Icon(if (mainTab == 1) Icons.Default.PersonAddAlt1 else Icons.Default.Add, contentDescription = "Add")
            }
        }
    ) { innerPadding ->
        Column(
            modifier = modifier
                .fillMaxSize()
                .background(Slate50)
                .padding(innerPadding)
        ) {
            // Main Section Tabs
            TabRow(
                selectedTabIndex = mainTab,
                containerColor = Color.White,
                contentColor = AuraBlue
            ) {
                Tab(
                    selected = mainTab == 0,
                    onClick = { mainTab = 0 },
                    text = {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Default.People, contentDescription = null, modifier = Modifier.size(16.dp))
                            Spacer(modifier = Modifier.width(4.dp))
                            Text("Leads (${leads.size})", fontWeight = if (mainTab == 0) FontWeight.Bold else FontWeight.Normal)
                        }
                    }
                )
                Tab(
                    selected = mainTab == 1,
                    onClick = { mainTab = 1 },
                    text = {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Default.DoorFront, contentDescription = null, modifier = Modifier.size(16.dp))
                            Spacer(modifier = Modifier.width(4.dp))
                            Text("Visitors (${visitors.size})", fontWeight = if (mainTab == 1) FontWeight.Bold else FontWeight.Normal)
                        }
                    }
                )
                Tab(
                    selected = mainTab == 2,
                    onClick = { mainTab = 2 },
                    text = {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Default.AccountTree, contentDescription = null, modifier = Modifier.size(16.dp))
                            Spacer(modifier = Modifier.width(4.dp))
                            Text("Pipeline Flow", fontWeight = if (mainTab == 2) FontWeight.Bold else FontWeight.Normal)
                        }
                    }
                )
            }

            // Search Bar (shown for Leads & Visitors)
            if (mainTab != 2) {
                OutlinedTextField(
                    value = searchQuery,
                    onValueChange = { searchQuery = it },
                    placeholder = { Text(if (mainTab == 0) "Search client name, phone, or architect..." else "Search visitor name, phone, requirements...") },
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
                        .padding(horizontal = 16.dp, vertical = 8.dp)
                        .testTag("leads_search_input")
                )

                // Division Filters
                DivisionFilterRow(
                    selectedDivision = selectedDivision,
                    onSelect = { selectedDivision = it }
                )
            }

            when (mainTab) {
                0 -> {
                    // Stage Filter Chips for Leads
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .horizontalScroll(rememberScrollState())
                            .padding(horizontal = 16.dp, vertical = 4.dp),
                        horizontalArrangement = Arrangement.spacedBy(6.dp)
                    ) {
                        FilterChip(
                            selected = selectedStageFilter == null,
                            onClick = { selectedStageFilter = null },
                            label = { Text("All Stages (${leads.size})", fontSize = 11.sp) },
                            colors = FilterChipDefaults.filterChipColors(
                                selectedContainerColor = Slate800,
                                selectedLabelColor = Color.White
                            )
                        )
                        LeadStage.values().forEach { stage ->
                            val count = leads.count { it.stage == stage }
                            FilterChip(
                                selected = selectedStageFilter == stage,
                                onClick = { selectedStageFilter = stage },
                                label = { Text("${stage.displayName} ($count)", fontSize = 11.sp) },
                                colors = FilterChipDefaults.filterChipColors(
                                    selectedContainerColor = AuraBlue,
                                    selectedLabelColor = Color.White
                                )
                            )
                        }
                    }

                    // Leads List
                    if (filteredLeads.isEmpty()) {
                        Box(
                            modifier = Modifier
                                .fillMaxSize()
                                .padding(32.dp),
                            contentAlignment = Alignment.Center
                        ) {
                            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                Icon(Icons.Default.PersonSearch, contentDescription = null, tint = Slate300, modifier = Modifier.size(64.dp))
                                Spacer(modifier = Modifier.height(12.dp))
                                Text("No leads match your filter", style = MaterialTheme.typography.titleMedium, color = Slate600)
                                Spacer(modifier = Modifier.height(6.dp))
                                Text("Try resetting filters or create a new lead", style = MaterialTheme.typography.bodySmall, color = Slate400)
                            }
                        }
                    } else {
                        LazyColumn(
                            modifier = Modifier.fillMaxSize(),
                            contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 8.dp, bottom = 80.dp),
                            verticalArrangement = Arrangement.spacedBy(10.dp)
                        ) {
                            items(filteredLeads, key = { it.id }) { lead ->
                                LeadCard(
                                    lead = lead,
                                    onStageChange = { newStage ->
                                        repository.updateLeadStage(lead.id, newStage)
                                    },
                                    onDelete = {
                                        repository.deleteLead(lead.id)
                                    },
                                    onCall = {
                                        val intent = Intent(Intent.ACTION_DIAL, Uri.parse("tel:${lead.phone}"))
                                        context.startActivity(intent)
                                    },
                                    onWhatsApp = {
                                        val cleanPhone = lead.phone.replace("[^0-9]".toRegex(), "")
                                        val intent = Intent(Intent.ACTION_VIEW, Uri.parse("https://wa.me/$cleanPhone"))
                                        context.startActivity(intent)
                                    },
                                    onConvertToQuote = { onConvertToQuote(lead) },
                                    onScheduleSurvey = { surveyTargetLead = lead },
                                    onViewJourney = { journeyTargetLead = lead }
                                )
                            }
                        }
                    }
                }

                1 -> {
                    // Showroom Visitors Tab
                    if (filteredVisitors.isEmpty()) {
                        Box(
                            modifier = Modifier
                                .fillMaxSize()
                                .padding(32.dp),
                            contentAlignment = Alignment.Center
                        ) {
                            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                Icon(Icons.Default.DoorFront, contentDescription = null, tint = Slate300, modifier = Modifier.size(64.dp))
                                Spacer(modifier = Modifier.height(12.dp))
                                Text("No visitors logged yet", style = MaterialTheme.typography.titleMedium, color = Slate600)
                                Spacer(modifier = Modifier.height(6.dp))
                                Button(
                                    onClick = { showAddVisitorDialog = true },
                                    colors = ButtonDefaults.buttonColors(containerColor = AuraBlue)
                                ) {
                                    Text("Log Showroom Visitor")
                                }
                            }
                        }
                    } else {
                        LazyColumn(
                            modifier = Modifier.fillMaxSize(),
                            contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 8.dp, bottom = 80.dp),
                            verticalArrangement = Arrangement.spacedBy(10.dp)
                        ) {
                            items(filteredVisitors, key = { it.id }) { visitor ->
                                VisitorCard(
                                    visitor = visitor,
                                    onConvertToLead = {
                                        val newLead = repository.convertVisitorToLead(visitor)
                                        toastMessage = "Visitor ${visitor.name} converted to Lead ${newLead.id}!"
                                    },
                                    onCall = {
                                        val intent = Intent(Intent.ACTION_DIAL, Uri.parse("tel:${visitor.phone}"))
                                        context.startActivity(intent)
                                    }
                                )
                            }
                        }
                    }
                }

                2 -> {
                    // Connected Pipeline Flow Diagram & Counters
                    LazyColumn(
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(16.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        item {
                            Card(
                                shape = RoundedCornerShape(16.dp),
                                colors = CardDefaults.cardColors(containerColor = Color.White),
                                elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
                            ) {
                                Column(modifier = Modifier.padding(16.dp)) {
                                    Row(verticalAlignment = Alignment.CenterVertically) {
                                        Icon(Icons.Default.Hub, contentDescription = null, tint = AuraBlue)
                                        Spacer(modifier = Modifier.width(8.dp))
                                        Text("MADIO Group Linked Pipeline", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = Slate900)
                                    }
                                    Text(
                                        "Seamless data chain tracking inquiries from walk-in to execution and site attendance",
                                        style = MaterialTheme.typography.bodySmall,
                                        color = Slate600,
                                        modifier = Modifier.padding(top = 4.dp)
                                    )
                                }
                            }
                        }

                        item {
                            FlowStageBanner(
                                step = "1",
                                title = "Showroom Visitors & Inquiries",
                                count = "${visitors.size} logged",
                                description = "Walk-in registration at reception desk with division preference",
                                icon = Icons.Default.DoorFront,
                                accentColor = Color(0xFF3B82F6)
                            )
                        }

                        item {
                            FlowConnectorArrow()
                        }

                        item {
                            FlowStageBanner(
                                step = "2",
                                title = "Sales Leads & CRM",
                                count = "${leads.size} active leads",
                                description = "Qualification, division tagging, follow-ups, and architect reference",
                                icon = Icons.Default.People,
                                accentColor = Color(0xFF8B5CF6)
                            )
                        }

                        item {
                            FlowConnectorArrow()
                        }

                        item {
                            FlowStageBanner(
                                step = "3",
                                title = "Site Surveys & Laser Measurement",
                                count = "${surveys.size} surveys",
                                description = "Substrate moisture testing, aperture measurements & site readiness",
                                icon = Icons.Default.SquareFoot,
                                accentColor = Color(0xFF06B6D4)
                            )
                        }

                        item {
                            FlowConnectorArrow()
                        }

                        item {
                            FlowStageBanner(
                                step = "4",
                                title = "Quotation Proposals",
                                count = "${quotes.size} quotes",
                                description = "Automated bill-of-quantities generated directly from survey specs",
                                icon = Icons.Default.RequestQuote,
                                accentColor = Color(0xFFF59E0B)
                            )
                        }

                        item {
                            FlowConnectorArrow()
                        }

                        item {
                            FlowStageBanner(
                                step = "5",
                                title = "Confirmed Sale & Booking",
                                count = "${sales.size} orders",
                                description = "Advance booking payment cleared, dispatch schedule locked",
                                icon = Icons.Default.ShoppingCart,
                                accentColor = Color(0xFF10B981)
                            )
                        }

                        item {
                            FlowConnectorArrow()
                        }

                        item {
                            FlowStageBanner(
                                step = "6",
                                title = "Project Execution & Milestones",
                                count = "${projects.size} active sites",
                                description = "Site PM assignment, installation milestones, and QA sign-off",
                                icon = Icons.Default.Construction,
                                accentColor = Color(0xFFEF4444)
                            )
                        }

                        item {
                            FlowConnectorArrow()
                        }

                        item {
                            FlowStageBanner(
                                step = "7",
                                title = "Project Petty Cash Wallets",
                                count = "${wallets.size} wallets",
                                description = "On-site engineer funds for hardware, daily labour, freight & tempo",
                                icon = Icons.Default.AccountBalanceWallet,
                                accentColor = Color(0xFF6366F1)
                            )
                        }

                        item {
                            FlowConnectorArrow()
                        }

                        item {
                            FlowStageBanner(
                                step = "8",
                                title = "Attendance with Location & Selfie",
                                count = "${repository.attendance.collectAsState().value.size} records",
                                description = "GPS geo-tagged on-site punch-in and live camera verification",
                                icon = Icons.Default.LocationOn,
                                accentColor = Color(0xFF059669)
                            )
                        }

                        item {
                            Spacer(modifier = Modifier.height(40.dp))
                        }
                    }
                }
            }
        }
    }

    // Dialogs
    if (showAddVisitorDialog) {
        AddVisitorDialog(
            onDismiss = { showAddVisitorDialog = false },
            onSave = { newVisitor ->
                repository.addVisitor(newVisitor)
                showAddVisitorDialog = false
                toastMessage = "Visitor ${newVisitor.name} logged successfully!"
            }
        )
    }

    if (surveyTargetLead != null) {
        ScheduleSurveyDialog(
            lead = surveyTargetLead,
            onDismiss = { surveyTargetLead = null },
            onSave = { newSurvey ->
                repository.addSurvey(newSurvey)
                repository.updateLeadStage(surveyTargetLead!!.id, LeadStage.SURVEY_NEEDED)
                surveyTargetLead = null
                toastMessage = "Site Survey recorded for ${newSurvey.clientName}!"
            }
        )
    }

    if (journeyTargetLead != null) {
        LeadJourneyDialog(
            lead = journeyTargetLead!!,
            repository = repository,
            onDismiss = { journeyTargetLead = null },
            onScheduleSurvey = {
                val l = journeyTargetLead
                journeyTargetLead = null
                surveyTargetLead = l
            },
            onCreateQuote = {
                val l = journeyTargetLead
                journeyTargetLead = null
                if (l != null) onConvertToQuote(l)
            },
            onViewProjects = {
                journeyTargetLead = null
                onNavigateToProjects()
            }
        )
    }

    if (toastMessage != null) {
        AlertDialog(
            onDismissRequest = { toastMessage = null },
            title = { Text("Pipeline Notification", fontWeight = FontWeight.Bold, color = AuraBlue) },
            text = { Text(toastMessage!!) },
            confirmButton = {
                Button(onClick = { toastMessage = null }, colors = ButtonDefaults.buttonColors(containerColor = AuraBlue)) {
                    Text("OK")
                }
            }
        )
    }
}

@Composable
fun LeadCard(
    lead: Lead,
    onStageChange: (LeadStage) -> Unit,
    onDelete: () -> Unit,
    onCall: () -> Unit,
    onWhatsApp: () -> Unit,
    onConvertToQuote: () -> Unit,
    onScheduleSurvey: () -> Unit,
    onViewJourney: () -> Unit,
    modifier: Modifier = Modifier
) {
    var showStageMenu by remember { mutableStateOf(false) }

    Card(
        colors = CardDefaults.cardColors(containerColor = Color.White),
        shape = RoundedCornerShape(16.dp),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
        modifier = modifier
            .fillMaxWidth()
            .testTag("lead_card_${lead.id}")
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            // Header Row: Name, Division & Stage
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(
                            text = lead.name,
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold,
                            color = Slate900
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        DivisionBadge(lead.division)
                    }
                    Text(
                        text = lead.phone,
                        style = MaterialTheme.typography.bodySmall,
                        color = Slate500
                    )
                }

                Box {
                    Surface(
                        shape = RoundedCornerShape(12.dp),
                        modifier = Modifier.clickable { showStageMenu = true }
                    ) {
                        LeadStageBadge(lead.stage)
                    }
                    DropdownMenu(
                        expanded = showStageMenu,
                        onDismissRequest = { showStageMenu = false }
                    ) {
                        LeadStage.values().forEach { stage ->
                            DropdownMenuItem(
                                text = { Text(stage.displayName) },
                                onClick = {
                                    onStageChange(stage)
                                    showStageMenu = false
                                }
                            )
                        }
                    }
                }
            }

            Spacer(modifier = Modifier.height(8.dp))

            // Details & Notes
            if (lead.remarks.isNotBlank()) {
                Surface(
                    color = Slate50,
                    shape = RoundedCornerShape(8.dp),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text(
                        text = lead.remarks,
                        style = MaterialTheme.typography.bodySmall,
                        color = Slate700,
                        modifier = Modifier.padding(8.dp)
                    )
                }
            }

            Spacer(modifier = Modifier.height(8.dp))

            // Metrics: Estimated Value, Source, Confidence
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column {
                    Text("Est. Value", style = MaterialTheme.typography.labelMedium, color = Slate400, fontSize = 10.sp)
                    Text(formatInr(lead.estimatedValue), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold, color = AuraBlue)
                }
                Column {
                    Text("Source", style = MaterialTheme.typography.labelMedium, color = Slate400, fontSize = 10.sp)
                    Text(lead.source, style = MaterialTheme.typography.bodySmall, fontWeight = FontWeight.Medium, color = Slate700)
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text("Confidence", style = MaterialTheme.typography.labelMedium, color = Slate400, fontSize = 10.sp)
                    Text("${lead.confidenceLevel}%", style = MaterialTheme.typography.bodySmall, fontWeight = FontWeight.Bold, color = SuccessGreen)
                }
            }

            Spacer(modifier = Modifier.height(10.dp))

            // Pipeline Linking Row
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(8.dp))
                    .background(Color(0xFFF1F5F9))
                    .clickable { onViewJourney() }
                    .padding(horizontal = 10.dp, vertical = 6.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Default.LinearScale, contentDescription = null, tint = AuraBlue, modifier = Modifier.size(16.dp))
                    Spacer(modifier = Modifier.width(6.dp))
                    Text("Lifecycle: Visitor ➔ Lead ➔ Survey ➔ Quote ➔ Project", fontSize = 10.sp, fontWeight = FontWeight.Medium, color = Slate700)
                }
                Icon(Icons.Default.ChevronRight, contentDescription = "View Journey", tint = Slate500, modifier = Modifier.size(16.dp))
            }

            Spacer(modifier = Modifier.height(10.dp))
            HorizontalDivider(color = Slate100)
            Spacer(modifier = Modifier.height(8.dp))

            // Action Buttons
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    FilledTonalIconButton(
                        onClick = onCall,
                        colors = IconButtonDefaults.filledTonalIconButtonColors(containerColor = Slate100),
                        modifier = Modifier.size(36.dp)
                    ) {
                        Icon(Icons.Default.Phone, contentDescription = "Call", tint = AuraBlue, modifier = Modifier.size(18.dp))
                    }
                    FilledTonalIconButton(
                        onClick = onWhatsApp,
                        colors = IconButtonDefaults.filledTonalIconButtonColors(containerColor = SuccessGreenLight),
                        modifier = Modifier.size(36.dp)
                    ) {
                        Icon(Icons.Default.Chat, contentDescription = "WhatsApp", tint = SuccessGreen, modifier = Modifier.size(18.dp))
                    }
                    IconButton(onClick = onDelete, modifier = Modifier.size(36.dp)) {
                        Icon(Icons.Default.DeleteOutline, contentDescription = "Delete", tint = Slate400, modifier = Modifier.size(18.dp))
                    }
                }

                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    OutlinedButton(
                        onClick = onScheduleSurvey,
                        shape = RoundedCornerShape(10.dp),
                        contentPadding = PaddingValues(horizontal = 10.dp, vertical = 4.dp),
                        colors = ButtonDefaults.outlinedButtonColors(contentColor = Slate700)
                    ) {
                        Icon(Icons.Default.SquareFoot, contentDescription = null, modifier = Modifier.size(14.dp))
                        Spacer(modifier = Modifier.width(4.dp))
                        Text("Survey", fontSize = 11.sp)
                    }

                    if (lead.stage != LeadStage.WON && lead.stage != LeadStage.LOST) {
                        Button(
                            onClick = onConvertToQuote,
                            colors = ButtonDefaults.buttonColors(containerColor = AuraBlue),
                            shape = RoundedCornerShape(10.dp),
                            contentPadding = PaddingValues(horizontal = 12.dp, vertical = 4.dp),
                            modifier = Modifier.testTag("convert_quote_button_${lead.id}")
                        ) {
                            Icon(Icons.Default.RequestQuote, contentDescription = null, modifier = Modifier.size(14.dp))
                            Spacer(modifier = Modifier.width(4.dp))
                            Text("Quote", fontSize = 11.sp)
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun VisitorCard(
    visitor: Visitor,
    onConvertToLead: () -> Unit,
    onCall: () -> Unit,
    modifier: Modifier = Modifier
) {
    val isConverted = visitor.status == "Converted to Lead"

    Card(
        colors = CardDefaults.cardColors(containerColor = Color.White),
        shape = RoundedCornerShape(16.dp),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
        modifier = modifier.fillMaxWidth()
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
                        text = "${visitor.phone} • ${visitor.checkInTime}",
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
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 3.dp)
                    )
                }
            }

            Spacer(modifier = Modifier.height(8.dp))

            Surface(
                color = Color(0xFFF8FAFC),
                shape = RoundedCornerShape(8.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(modifier = Modifier.padding(10.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Default.ShoppingBag, contentDescription = null, tint = AuraBlue, modifier = Modifier.size(14.dp))
                        Spacer(modifier = Modifier.width(6.dp))
                        Text("Interested In: ${visitor.interestedIn}", fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = Slate800)
                    }
                    if (visitor.notes.isNotBlank()) {
                        Spacer(modifier = Modifier.height(4.dp))
                        Text("Notes: ${visitor.notes}", fontSize = 11.sp, color = Slate600)
                    }
                    Spacer(modifier = Modifier.height(4.dp))
                    Text("Attended by: ${visitor.attendedBy} • Purpose: ${visitor.purpose}", fontSize = 10.sp, color = Slate500)
                }
            }

            Spacer(modifier = Modifier.height(10.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                FilledTonalIconButton(
                    onClick = onCall,
                    colors = IconButtonDefaults.filledTonalIconButtonColors(containerColor = Slate100),
                    modifier = Modifier.size(36.dp)
                ) {
                    Icon(Icons.Default.Phone, contentDescription = "Call", tint = AuraBlue, modifier = Modifier.size(18.dp))
                }

                if (!isConverted) {
                    Button(
                        onClick = onConvertToLead,
                        colors = ButtonDefaults.buttonColors(containerColor = AuraBlue),
                        shape = RoundedCornerShape(10.dp),
                        contentPadding = PaddingValues(horizontal = 14.dp, vertical = 6.dp)
                    ) {
                        Icon(Icons.Default.PersonAdd, contentDescription = null, modifier = Modifier.size(16.dp))
                        Spacer(modifier = Modifier.width(6.dp))
                        Text("Convert to Lead", fontSize = 12.sp, fontWeight = FontWeight.Bold)
                    }
                } else {
                    Text(
                        text = "Linked to Lead ${visitor.convertedLeadId ?: ""}",
                        fontSize = 12.sp,
                        fontWeight = FontWeight.SemiBold,
                        color = SuccessGreen
                    )
                }
            }
        }
    }
}

@Composable
fun FlowStageBanner(
    step: String,
    title: String,
    count: String,
    description: String,
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    accentColor: Color
) {
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
            Box(
                modifier = Modifier
                    .size(42.dp)
                    .clip(RoundedCornerShape(10.dp))
                    .background(accentColor.copy(alpha = 0.12f)),
                contentAlignment = Alignment.Center
            ) {
                Icon(icon, contentDescription = null, tint = accentColor, modifier = Modifier.size(22.dp))
            }

            Spacer(modifier = Modifier.width(12.dp))

            Column(modifier = Modifier.weight(1f)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "$step. $title",
                        fontWeight = FontWeight.Bold,
                        style = MaterialTheme.typography.bodyMedium,
                        color = Slate900
                    )
                    Surface(
                        color = accentColor.copy(alpha = 0.1f),
                        shape = RoundedCornerShape(4.dp)
                    ) {
                        Text(
                            text = count,
                            fontSize = 11.sp,
                            fontWeight = FontWeight.Bold,
                            color = accentColor,
                            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                        )
                    }
                }
                Text(
                    text = description,
                    style = MaterialTheme.typography.bodySmall,
                    color = Slate600,
                    fontSize = 11.sp
                )
            }
        }
    }
}

@Composable
fun FlowConnectorArrow() {
    Box(
        modifier = Modifier.fillMaxWidth(),
        contentAlignment = Alignment.Center
    ) {
        Icon(
            Icons.Default.ArrowDownward,
            contentDescription = null,
            tint = Slate400,
            modifier = Modifier.size(18.dp)
        )
    }
}

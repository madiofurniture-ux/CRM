package com.example.madiocrm.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowForward
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.madiocrm.data.model.Division
import com.example.madiocrm.data.model.LeadStage
import com.example.madiocrm.data.repository.CrmRepository
import com.example.madiocrm.ui.components.*
import com.example.madiocrm.ui.theme.*

@Composable
fun DashboardScreen(
    repository: CrmRepository,
    onNavigateToLeads: () -> Unit,
    onNavigateToQuotes: () -> Unit,
    onNavigateToSales: () -> Unit,
    onNavigateToProjects: () -> Unit,
    onNavigateToInventory: () -> Unit,
    onOpenAddLead: () -> Unit,
    onNavigateToChat: (() -> Unit)? = null,
    modifier: Modifier = Modifier
) {
    val leads by repository.leads.collectAsState()
    val quotes by repository.quotes.collectAsState()
    val sales by repository.sales.collectAsState()
    val projects by repository.projects.collectAsState()
    val inventory by repository.inventory.collectAsState()
    val tasks by repository.tasks.collectAsState()
    val chatGroups by repository.chatGroups.collectAsState()

    var selectedDivision by remember { mutableStateOf(Division.ALL) }

    val filteredLeads = remember(leads, selectedDivision) {
        if (selectedDivision == Division.ALL) leads else leads.filter { it.division == selectedDivision }
    }
    val filteredSales = remember(sales, selectedDivision) {
        if (selectedDivision == Division.ALL) sales else sales.filter { it.division == selectedDivision }
    }
    val filteredQuotes = remember(quotes, selectedDivision) {
        if (selectedDivision == Division.ALL) quotes else quotes.filter { it.division == selectedDivision }
    }
    val filteredProjects = remember(projects, selectedDivision) {
        if (selectedDivision == Division.ALL) projects else projects.filter { it.division == selectedDivision }
    }

    val totalBookedSales = filteredSales.sumOf { it.totalValue }
    val totalCollected = filteredSales.sumOf { it.paidAmount }
    val pendingReceivables = totalBookedSales - totalCollected
    val activeLeadsCount = filteredLeads.count { it.stage != LeadStage.LOST && it.stage != LeadStage.WON }
    val activeProjectsCount = filteredProjects.count { it.stage != "Completed" }
    val pendingTasksCount = tasks.count { !it.isDone }

    LazyColumn(
        modifier = modifier
            .fillMaxSize()
            .background(Slate50),
        contentPadding = PaddingValues(bottom = 90.dp)
    ) {
        // Hero Header
        item {
            Card(
                colors = CardDefaults.cardColors(containerColor = AuraBlue),
                shape = RoundedCornerShape(bottomStart = 24.dp, bottomEnd = 24.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 20.dp, vertical = 20.dp)
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column {
                            Text(
                                text = "MADIO GROUP CRM",
                                style = MaterialTheme.typography.labelMedium,
                                color = Color.White.copy(alpha = 0.8f),
                                letterSpacing = 1.sp,
                                fontWeight = FontWeight.Bold
                            )
                            Text(
                                text = "Executive Overview",
                                style = MaterialTheme.typography.headlineMedium,
                                color = Color.White,
                                fontWeight = FontWeight.Bold
                            )
                        }
                        // Quick Add Lead button
                        FilledTonalButton(
                            onClick = onOpenAddLead,
                            colors = ButtonDefaults.filledTonalButtonColors(
                                containerColor = GoldAccent,
                                contentColor = Color.White
                            ),
                            shape = RoundedCornerShape(12.dp),
                            modifier = Modifier.testTag("quick_add_lead_button")
                        ) {
                            Icon(Icons.Default.Add, contentDescription = null, modifier = Modifier.size(18.dp))
                            Spacer(modifier = Modifier.width(4.dp))
                            Text("New Lead", fontWeight = FontWeight.SemiBold)
                        }
                    }

                    Spacer(modifier = Modifier.height(16.dp))

                    // Revenue Snapshot Banner
                    Surface(
                        color = Color.White.copy(alpha = 0.12f),
                        shape = RoundedCornerShape(16.dp),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(16.dp),
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Column {
                                Text("Total Booked Sales", color = Color.White.copy(alpha = 0.8f), style = MaterialTheme.typography.bodySmall)
                                Text(formatInr(totalBookedSales), color = Color.White, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                            }
                            Column {
                                Text("Collected", color = Color.White.copy(alpha = 0.8f), style = MaterialTheme.typography.bodySmall)
                                Text(formatInr(totalCollected), color = SuccessGreenLight, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                            }
                            Column {
                                Text("Receivables", color = Color.White.copy(alpha = 0.8f), style = MaterialTheme.typography.bodySmall)
                                Text(formatInr(pendingReceivables), color = WarningAmberLight, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                            }
                        }
                    }
                }
            }
        }

        // Division Filter Chips
        item {
            DivisionFilterRow(
                selectedDivision = selectedDivision,
                onSelect = { selectedDivision = it },
                modifier = Modifier.padding(top = 10.dp)
            )
        }

        // Key Business Metrics Grid
        item {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 6.dp)
            ) {
                Text(
                    text = "Operational Pulse",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = Slate800,
                    modifier = Modifier.padding(bottom = 10.dp)
                )

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    KpiCard(
                        title = "Active Leads",
                        value = "$activeLeadsCount In Pipeline",
                        subtitle = "${filteredLeads.size} Total Leads",
                        icon = Icons.Default.People,
                        iconBgColor = AuraBlueLight,
                        iconTint = AuraBlue,
                        modifier = Modifier
                            .weight(1f)
                            .clickable { onNavigateToLeads() }
                    )
                    KpiCard(
                        title = "Quotes Active",
                        value = "${filteredQuotes.size} Proposals",
                        subtitle = formatInr(filteredQuotes.sumOf { it.grandTotal }),
                        icon = Icons.Default.Description,
                        iconBgColor = GoldLight,
                        iconTint = Color(0xFFB45309),
                        modifier = Modifier
                            .weight(1f)
                            .clickable { onNavigateToQuotes() }
                    )
                }

                Spacer(modifier = Modifier.height(12.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    KpiCard(
                        title = "Site Projects",
                        value = "$activeProjectsCount Active",
                        subtitle = "${filteredProjects.size} Sites Monitored",
                        icon = Icons.Default.Engineering,
                        iconBgColor = SuccessGreenLight,
                        iconTint = SuccessGreen,
                        modifier = Modifier
                            .weight(1f)
                            .clickable { onNavigateToProjects() }
                    )
                    KpiCard(
                        title = "Pending Tasks",
                        value = "$pendingTasksCount Action Items",
                        subtitle = "Follow-ups & SNAGs",
                        icon = Icons.Default.AssignmentLate,
                        iconBgColor = DangerRedLight,
                        iconTint = DangerRed,
                        modifier = Modifier.weight(1f)
                    )
                }
            }
        }

        // WhatsApp Project Chat & Confidential Discussions Hub
        item {
            val totalUnread = chatGroups.sumOf { it.unreadCount }
            val linkedProjectsCount = chatGroups.count { it.projectId != null }

            Card(
                colors = CardDefaults.cardColors(containerColor = Color.White),
                shape = RoundedCornerShape(16.dp),
                elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 6.dp)
                    .clickable { onNavigateToChat?.invoke() }
                    .testTag("dashboard_chat_card")
            ) {
                Row(
                    modifier = Modifier.padding(16.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Box(
                        modifier = Modifier
                            .size(46.dp)
                            .clip(CircleShape)
                            .background(Color(0xFF075E54)),
                        contentAlignment = Alignment.Center
                    ) {
                        Icon(
                            Icons.Default.Forum,
                            contentDescription = null,
                            tint = Color.White,
                            modifier = Modifier.size(24.dp)
                        )
                    }

                    Spacer(modifier = Modifier.width(12.dp))

                    Column(modifier = Modifier.weight(1f)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(
                                "MADIO Team WhatsApp Chat",
                                fontWeight = FontWeight.Bold,
                                style = MaterialTheme.typography.titleSmall,
                                color = Slate900
                            )
                            Spacer(modifier = Modifier.width(4.dp))
                            Icon(Icons.Default.Lock, contentDescription = null, tint = Color(0xFFD97706), modifier = Modifier.size(12.dp))
                        }
                        Text(
                            "$linkedProjectsCount Project Rooms • Confidential site photos, BoQs & drawings",
                            fontSize = 11.sp,
                            color = Slate500
                        )
                    }

                    if (totalUnread > 0) {
                        Surface(
                            color = Color(0xFF25D366),
                            shape = CircleShape
                        ) {
                            Text(
                                text = "$totalUnread new",
                                color = Color.White,
                                fontSize = 10.sp,
                                fontWeight = FontWeight.Bold,
                                modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                            )
                        }
                    } else {
                        Icon(
                            Icons.Default.ChevronRight,
                            contentDescription = null,
                            tint = Slate400,
                            modifier = Modifier.size(20.dp)
                        )
                    }
                }
            }
        }

        // Urgent Action Alerts
        item {
            val urgentLeads = leads.filter { it.stage == LeadStage.QUOTED || it.confidenceLevel >= 80 }.take(2)
            if (urgentLeads.isNotEmpty()) {
                Card(
                    colors = CardDefaults.cardColors(containerColor = Color.White),
                    shape = RoundedCornerShape(16.dp),
                    elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp, vertical = 8.dp)
                ) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.SpaceBetween,
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Box(
                                    modifier = Modifier
                                        .size(10.dp)
                                        .clip(CircleShape)
                                        .background(DangerRed)
                                )
                                Spacer(modifier = Modifier.width(8.dp))
                                Text(
                                    text = "High Priority Follow-ups",
                                    style = MaterialTheme.typography.titleSmall,
                                    fontWeight = FontWeight.Bold,
                                    color = Slate900
                                )
                            }
                            TextButton(onClick = onNavigateToLeads) {
                                Text("View All", color = AuraBlue, style = MaterialTheme.typography.labelMedium)
                            }
                        }

                        urgentLeads.forEach { lead ->
                            HorizontalDivider(modifier = Modifier.padding(vertical = 8.dp), color = Slate100)
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Column(modifier = Modifier.weight(1f)) {
                                    Row(verticalAlignment = Alignment.CenterVertically) {
                                        Text(lead.name, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyMedium)
                                        Spacer(modifier = Modifier.width(6.dp))
                                        DivisionBadge(lead.division)
                                    }
                                    Text(
                                        text = "${lead.remarks} | Due: ${lead.followUpDate}",
                                        style = MaterialTheme.typography.bodySmall,
                                        color = Slate500,
                                        maxLines = 1
                                    )
                                }
                                Text(
                                    text = formatInr(lead.estimatedValue),
                                    style = MaterialTheme.typography.labelLarge,
                                    fontWeight = FontWeight.Bold,
                                    color = AuraBlue
                                )
                            }
                        }
                    }
                }
            }
        }

        // Active Projects Progress Section
        item {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 8.dp)
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "Ongoing Site Execution",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        color = Slate800
                    )
                    TextButton(onClick = onNavigateToProjects) {
                        Text("All Projects", color = AuraBlue)
                        Icon(Icons.AutoMirrored.Filled.ArrowForward, contentDescription = null, modifier = Modifier.size(16.dp))
                    }
                }

                filteredProjects.take(2).forEach { project ->
                    Card(
                        colors = CardDefaults.cardColors(containerColor = Color.White),
                        shape = RoundedCornerShape(14.dp),
                        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 4.dp)
                            .clickable { onNavigateToProjects() }
                    ) {
                        Column(modifier = Modifier.padding(14.dp)) {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Text(project.customerName, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyMedium)
                                    Spacer(modifier = Modifier.width(8.dp))
                                    DivisionBadge(project.division)
                                }
                                Text("${project.completionPct}%", fontWeight = FontWeight.Bold, color = AuraBlue)
                            }
                            Spacer(modifier = Modifier.height(6.dp))
                            LinearProgressIndicator(
                                progress = { project.completionPct / 100f },
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .height(6.dp)
                                    .clip(RoundedCornerShape(3.dp)),
                                color = AuraBlue,
                                trackColor = Slate200
                            )
                            Spacer(modifier = Modifier.height(6.dp))
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween
                            ) {
                                Text("Stage: ${project.stage}", style = MaterialTheme.typography.bodySmall, color = Slate600)
                                Text("Eng: ${project.assignedEngineer}", style = MaterialTheme.typography.bodySmall, color = Slate500)
                            }
                        }
                    }
                }
            }
        }
    }
}

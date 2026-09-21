package com.example.madiocrm.ui.screens

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.background
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
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.madiocrm.data.model.Division
import com.example.madiocrm.data.model.Project
import com.example.madiocrm.data.model.ProjectExpense
import com.example.madiocrm.data.model.ProjectWallet
import com.example.madiocrm.data.repository.CrmRepository
import com.example.madiocrm.ui.components.*
import com.example.madiocrm.ui.theme.*

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ProjectsScreen(
    repository: CrmRepository,
    onOpenProjectChat: ((Project) -> Unit)? = null,
    onOpenAllChats: (() -> Unit)? = null,
    modifier: Modifier = Modifier
) {
    val projects by repository.projects.collectAsState()
    val wallets by repository.projectWallets.collectAsState()
    val projectExpenses by repository.projectExpenses.collectAsState()

    var activeTab by remember { mutableIntStateOf(0) } // 0: Projects, 1: Project Wallets
    var selectedDivision by remember { mutableStateOf(Division.ALL) }

    var expenseTargetWallet by remember { mutableStateOf<ProjectWallet?>(null) }
    var topupTargetWallet by remember { mutableStateOf<ProjectWallet?>(null) }

    val filteredProjects = remember(projects, selectedDivision) {
        if (selectedDivision == Division.ALL) projects else projects.filter { it.division == selectedDivision }
    }

    val filteredWallets = remember(wallets, selectedDivision) {
        if (selectedDivision == Division.ALL) wallets else wallets.filter { it.division == selectedDivision }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text("Project Execution & Site Wallets", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleLarge)
                        Text(
                            if (activeTab == 0) "${filteredProjects.size} sites under execution" else "${filteredWallets.size} project petty cash wallets",
                            style = MaterialTheme.typography.bodySmall,
                            color = Slate500
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = Color.White),
                actions = {
                    IconButton(
                        onClick = { onOpenAllChats?.invoke() },
                        modifier = Modifier.testTag("projects_top_chat_btn")
                    ) {
                        BadgedBox(
                            badge = {
                                Badge(
                                    containerColor = Color(0xFF25D366)
                                ) {
                                    Text("5", color = Color.White, fontSize = 9.sp)
                                }
                            }
                        ) {
                            Icon(Icons.Default.Forum, contentDescription = "Team Chats", tint = Color(0xFF075E54))
                        }
                    }
                }
            )
        }
    ) { innerPadding ->
        Column(
            modifier = modifier
                .fillMaxSize()
                .background(Slate50)
                .padding(innerPadding)
        ) {
            TabRow(
                selectedTabIndex = activeTab,
                containerColor = Color.White,
                contentColor = AuraBlue
            ) {
                Tab(
                    selected = activeTab == 0,
                    onClick = { activeTab = 0 },
                    text = {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Default.Construction, contentDescription = null, modifier = Modifier.size(16.dp))
                            Spacer(modifier = Modifier.width(6.dp))
                            Text("Execution Sites (${projects.size})", fontWeight = if (activeTab == 0) FontWeight.Bold else FontWeight.Normal)
                        }
                    }
                )
                Tab(
                    selected = activeTab == 1,
                    onClick = { activeTab = 1 },
                    text = {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Default.AccountBalanceWallet, contentDescription = null, modifier = Modifier.size(16.dp))
                            Spacer(modifier = Modifier.width(6.dp))
                            Text("Project Wallets (${wallets.size})", fontWeight = if (activeTab == 1) FontWeight.Bold else FontWeight.Normal)
                        }
                    }
                )
            }

            DivisionFilterRow(
                selectedDivision = selectedDivision,
                onSelect = { selectedDivision = it }
            )

            if (activeTab == 0) {
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 8.dp, bottom = 80.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    items(filteredProjects, key = { it.id }) { project ->
                        val linkedWallet = wallets.find { it.projectId == project.id || it.projectNo == project.projectNo }
                        ProjectCard(
                            project = project,
                            wallet = linkedWallet,
                            onMilestoneToggle = { index, completed ->
                                repository.updateProjectMilestone(project.id, index, completed)
                            },
                            onAddExpense = {
                                if (linkedWallet != null) {
                                    expenseTargetWallet = linkedWallet
                                }
                            },
                            onOpenProjectChat = {
                                onOpenProjectChat?.invoke(project)
                            }
                        )
                    }
                }
            } else {
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 8.dp, bottom = 80.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    // Total Petty Cash Metrics
                    item {
                        val totalAllocated = wallets.sumOf { it.totalAllocated }
                        val totalSpent = wallets.sumOf { it.totalSpent }
                        val totalAvailable = totalAllocated - totalSpent

                        Card(
                            colors = CardDefaults.cardColors(containerColor = Color.White),
                            shape = RoundedCornerShape(16.dp),
                            elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
                        ) {
                            Column(modifier = Modifier.padding(16.dp)) {
                                Text("Project Petty Cash Summary", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium, color = Slate900)
                                Spacer(modifier = Modifier.height(10.dp))
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.SpaceBetween
                                ) {
                                    Column {
                                        Text("Total Allocated", style = MaterialTheme.typography.labelSmall, color = Slate500)
                                        Text(formatInr(totalAllocated), fontWeight = FontWeight.Bold, color = Slate800, style = MaterialTheme.typography.titleMedium)
                                    }
                                    Column {
                                        Text("Total Spent", style = MaterialTheme.typography.labelSmall, color = Slate500)
                                        Text(formatInr(totalSpent), fontWeight = FontWeight.Bold, color = DangerRed, style = MaterialTheme.typography.titleMedium)
                                    }
                                    Column(horizontalAlignment = Alignment.End) {
                                        Text("Available Cash", style = MaterialTheme.typography.labelSmall, color = Slate500)
                                        Text(formatInr(totalAvailable), fontWeight = FontWeight.Bold, color = SuccessGreen, style = MaterialTheme.typography.titleMedium)
                                    }
                                }
                            }
                        }
                    }

                    items(filteredWallets, key = { it.id }) { wallet ->
                        val walletExpenses = projectExpenses.filter { it.walletId == wallet.id }
                        ProjectWalletCard(
                            wallet = wallet,
                            expenses = walletExpenses,
                            onAddExpense = { expenseTargetWallet = wallet },
                            onTopup = { topupTargetWallet = wallet }
                        )
                    }
                }
            }
        }
    }

    if (expenseTargetWallet != null) {
        AddProjectExpenseDialog(
            wallet = expenseTargetWallet!!,
            onDismiss = { expenseTargetWallet = null },
            onSave = { newExpense ->
                repository.addProjectExpense(newExpense)
                expenseTargetWallet = null
            }
        )
    }

    if (topupTargetWallet != null) {
        TopupProjectWalletDialog(
            wallet = topupTargetWallet!!,
            onDismiss = { topupTargetWallet = null },
            onSave = { amount ->
                repository.allocateToProjectWallet(topupTargetWallet!!.id, amount)
                topupTargetWallet = null
            }
        )
    }
}

@Composable
fun ProjectCard(
    project: Project,
    wallet: ProjectWallet?,
    onMilestoneToggle: (Int, Boolean) -> Unit,
    onAddExpense: () -> Unit,
    onOpenProjectChat: (() -> Unit)? = null,
    modifier: Modifier = Modifier
) {
    var isExpanded by remember { mutableStateOf(true) }

    Card(
        colors = CardDefaults.cardColors(containerColor = Color.White),
        shape = RoundedCornerShape(16.dp),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
        modifier = modifier
            .fillMaxWidth()
            .testTag("project_card_${project.id}")
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            // Header
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(project.projectNo, style = MaterialTheme.typography.labelLarge, color = AuraBlue, fontWeight = FontWeight.Bold)
                        Spacer(modifier = Modifier.width(6.dp))
                        DivisionBadge(project.division)
                    }
                    Text(project.customerName, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = Slate900)
                }

                Surface(
                    color = when {
                        project.completionPct >= 100 -> SuccessGreenLight
                        project.completionPct >= 50 -> AuraBlueLight
                        else -> WarningAmberLight
                    },
                    shape = RoundedCornerShape(12.dp)
                ) {
                    Text(
                        "${project.completionPct}% Complete",
                        color = when {
                            project.completionPct >= 100 -> SuccessGreen
                            project.completionPct >= 50 -> AuraBlue
                            else -> Color(0xFFB45309)
                        },
                        fontWeight = FontWeight.Bold,
                        style = MaterialTheme.typography.labelMedium,
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                    )
                }
            }

            Spacer(modifier = Modifier.height(8.dp))

            // Progress Bar
            LinearProgressIndicator(
                progress = { project.completionPct / 100f },
                modifier = Modifier
                    .fillMaxWidth()
                    .height(6.dp)
                    .clip(RoundedCornerShape(3.dp)),
                color = AuraBlue,
                trackColor = Slate200
            )

            Spacer(modifier = Modifier.height(10.dp))

            // Site & Engineer info
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Default.LocationOn, contentDescription = null, tint = Slate400, modifier = Modifier.size(16.dp))
                Spacer(modifier = Modifier.width(4.dp))
                Text(project.siteAddress, style = MaterialTheme.typography.bodySmall, color = Slate600, maxLines = 1)
            }

            Spacer(modifier = Modifier.height(4.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Default.Engineering, contentDescription = null, tint = Slate400, modifier = Modifier.size(16.dp))
                    Spacer(modifier = Modifier.width(4.dp))
                    Text(project.assignedEngineer, style = MaterialTheme.typography.bodySmall, color = Slate700)
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Default.Event, contentDescription = null, tint = Slate400, modifier = Modifier.size(16.dp))
                    Spacer(modifier = Modifier.width(4.dp))
                    Text("Target: ${project.targetDate}", style = MaterialTheme.typography.bodySmall, color = Slate500)
                }
            }

            // Linked Project Wallet Highlight Bar
            if (wallet != null) {
                Spacer(modifier = Modifier.height(10.dp))
                Surface(
                    color = Color(0xFFF1F5F9),
                    shape = RoundedCornerShape(8.dp),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Row(
                        modifier = Modifier.padding(10.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Icon(Icons.Default.AccountBalanceWallet, contentDescription = null, tint = AuraBlue, modifier = Modifier.size(14.dp))
                                Spacer(modifier = Modifier.width(4.dp))
                                Text("Petty Cash Wallet", fontSize = 11.sp, fontWeight = FontWeight.Bold, color = Slate800)
                            }
                            Text(
                                "Spent ${formatInr(wallet.totalSpent)} of ${formatInr(wallet.totalAllocated)} (Balance: ${formatInr(wallet.balance)})",
                                fontSize = 10.sp,
                                color = Slate600
                            )
                        }

                        OutlinedButton(
                            onClick = onAddExpense,
                            shape = RoundedCornerShape(8.dp),
                            contentPadding = PaddingValues(horizontal = 8.dp, vertical = 2.dp),
                            colors = ButtonDefaults.outlinedButtonColors(contentColor = AuraBlue)
                        ) {
                            Icon(Icons.Default.Add, contentDescription = null, modifier = Modifier.size(12.dp))
                            Spacer(modifier = Modifier.width(4.dp))
                            Text("Site Expense", fontSize = 10.sp)
                        }
                    }
                }
            }

            Spacer(modifier = Modifier.height(10.dp))

            // Action Buttons: WhatsApp Project Chat & Site Expense
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                OutlinedButton(
                    onClick = { onOpenProjectChat?.invoke() },
                    shape = RoundedCornerShape(8.dp),
                    contentPadding = PaddingValues(horizontal = 10.dp, vertical = 4.dp),
                    colors = ButtonDefaults.outlinedButtonColors(
                        contentColor = Color(0xFF075E54)
                    ),
                    modifier = Modifier
                        .weight(1f)
                        .testTag("project_chat_btn_${project.id}")
                ) {
                    Icon(
                        Icons.Default.Forum,
                        contentDescription = null,
                        modifier = Modifier.size(14.dp),
                        tint = Color(0xFF25D366)
                    )
                    Spacer(modifier = Modifier.width(6.dp))
                    Text("Project Chat", fontSize = 11.sp, fontWeight = FontWeight.Bold)
                }

                if (wallet != null) {
                    OutlinedButton(
                        onClick = onAddExpense,
                        shape = RoundedCornerShape(8.dp),
                        contentPadding = PaddingValues(horizontal = 10.dp, vertical = 4.dp),
                        colors = ButtonDefaults.outlinedButtonColors(contentColor = AuraBlue),
                        modifier = Modifier
                            .weight(1f)
                            .testTag("project_add_expense_btn_${project.id}")
                    ) {
                        Icon(Icons.Default.Add, contentDescription = null, modifier = Modifier.size(14.dp))
                        Spacer(modifier = Modifier.width(6.dp))
                        Text("Site Expense", fontSize = 11.sp, fontWeight = FontWeight.Bold)
                    }
                }
            }

            Spacer(modifier = Modifier.height(8.dp))
            HorizontalDivider(color = Slate100)
            Spacer(modifier = Modifier.height(8.dp))

            // Milestones Expand/Collapse Header
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable { isExpanded = !isExpanded },
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    "Execution Milestones (${project.milestones.count { it.completed }}/${project.milestones.size})",
                    style = MaterialTheme.typography.labelLarge,
                    fontWeight = FontWeight.Bold,
                    color = Slate800
                )
                Icon(
                    imageVector = if (isExpanded) Icons.Default.ExpandLess else Icons.Default.ExpandMore,
                    contentDescription = null,
                    tint = Slate500
                )
            }

            AnimatedVisibility(visible = isExpanded) {
                Column(modifier = Modifier.padding(top = 8.dp)) {
                    project.milestones.forEachIndexed { index, milestone ->
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(vertical = 2.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Checkbox(
                                checked = milestone.completed,
                                onCheckedChange = { checked ->
                                    onMilestoneToggle(index, checked)
                                },
                                colors = CheckboxDefaults.colors(
                                    checkedColor = SuccessGreen,
                                    checkmarkColor = Color.White
                                ),
                                modifier = Modifier.testTag("milestone_checkbox_${project.id}_$index")
                            )
                            Column(modifier = Modifier.weight(1f)) {
                                Text(
                                    text = milestone.title,
                                    style = MaterialTheme.typography.bodyMedium,
                                    fontWeight = if (milestone.completed) FontWeight.Normal else FontWeight.Medium,
                                    color = if (milestone.completed) Slate400 else Slate800
                                )
                                if (milestone.completed && milestone.completedAt.isNotBlank()) {
                                    Text("Completed ${milestone.completedAt}", style = MaterialTheme.typography.bodySmall, color = SuccessGreen, fontSize = 10.sp)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun ProjectWalletCard(
    wallet: ProjectWallet,
    expenses: List<ProjectExpense>,
    onAddExpense: () -> Unit,
    onTopup: () -> Unit,
    modifier: Modifier = Modifier
) {
    var isHistoryExpanded by remember { mutableStateOf(false) }

    Card(
        colors = CardDefaults.cardColors(containerColor = Color.White),
        shape = RoundedCornerShape(16.dp),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
        modifier = modifier.fillMaxWidth()
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            // Header
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(wallet.projectNo, style = MaterialTheme.typography.labelLarge, color = AuraBlue, fontWeight = FontWeight.Bold)
                        Spacer(modifier = Modifier.width(6.dp))
                        DivisionBadge(wallet.division)
                    }
                    Text(wallet.projectName, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = Slate900)
                    Text("Engineer: ${wallet.engineerName}", style = MaterialTheme.typography.bodySmall, color = Slate500)
                }

                Column(horizontalAlignment = Alignment.End) {
                    Text("Available Balance", style = MaterialTheme.typography.labelSmall, color = Slate500)
                    Text(
                        formatInr(wallet.balance),
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold,
                        color = if (wallet.balance > 2000) SuccessGreen else DangerRed
                    )
                }
            }

            Spacer(modifier = Modifier.height(12.dp))

            // Utilization Bar
            val pctSpent = if (wallet.totalAllocated > 0) (wallet.totalSpent / wallet.totalAllocated).toFloat() else 0f
            LinearProgressIndicator(
                progress = { pctSpent.coerceIn(0f, 1f) },
                modifier = Modifier
                    .fillMaxWidth()
                    .height(6.dp)
                    .clip(RoundedCornerShape(3.dp)),
                color = if (pctSpent > 0.8f) DangerRed else AuraBlue,
                trackColor = Slate200
            )

            Spacer(modifier = Modifier.height(8.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Text("Allocated: ${formatInr(wallet.totalAllocated)}", style = MaterialTheme.typography.bodySmall, color = Slate600)
                Text("Spent: ${formatInr(wallet.totalSpent)} (${(pctSpent * 100).toInt()}%)", style = MaterialTheme.typography.bodySmall, color = Slate600)
            }

            Spacer(modifier = Modifier.height(12.dp))

            // Action Buttons
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Button(
                    onClick = onAddExpense,
                    colors = ButtonDefaults.buttonColors(containerColor = AuraBlue),
                    shape = RoundedCornerShape(8.dp),
                    modifier = Modifier.weight(1f)
                ) {
                    Icon(Icons.Default.Add, contentDescription = null, modifier = Modifier.size(16.dp))
                    Spacer(modifier = Modifier.width(4.dp))
                    Text("Record Expense", fontSize = 12.sp)
                }

                OutlinedButton(
                    onClick = onTopup,
                    shape = RoundedCornerShape(8.dp),
                    colors = ButtonDefaults.outlinedButtonColors(contentColor = Slate800),
                    modifier = Modifier.weight(1f)
                ) {
                    Icon(Icons.Default.ArrowUpward, contentDescription = null, modifier = Modifier.size(16.dp))
                    Spacer(modifier = Modifier.width(4.dp))
                    Text("Top-up Wallet", fontSize = 12.sp)
                }
            }

            // Expense History Toggle
            if (expenses.isNotEmpty()) {
                Spacer(modifier = Modifier.height(10.dp))
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { isHistoryExpanded = !isHistoryExpanded },
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("On-Site Expense Logs (${expenses.size})", fontSize = 11.sp, fontWeight = FontWeight.SemiBold, color = Slate700)
                    Icon(if (isHistoryExpanded) Icons.Default.ExpandLess else Icons.Default.ExpandMore, contentDescription = null, tint = Slate500, modifier = Modifier.size(16.dp))
                }

                AnimatedVisibility(visible = isHistoryExpanded) {
                    Column(modifier = Modifier.padding(top = 6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        expenses.forEach { exp ->
                            Surface(
                                color = Color(0xFFF8FAFC),
                                shape = RoundedCornerShape(6.dp),
                                modifier = Modifier.fillMaxWidth()
                            ) {
                                Row(
                                    modifier = Modifier.padding(8.dp),
                                    horizontalArrangement = Arrangement.SpaceBetween,
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Column(modifier = Modifier.weight(1f)) {
                                        Text(exp.description, fontSize = 11.sp, fontWeight = FontWeight.Medium, color = Slate800)
                                        Text("${exp.date} • ${exp.category} • Paid to: ${exp.paidTo}", fontSize = 9.sp, color = Slate500)
                                    }
                                    Text(formatInr(exp.amount), fontSize = 11.sp, fontWeight = FontWeight.Bold, color = DangerRed)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

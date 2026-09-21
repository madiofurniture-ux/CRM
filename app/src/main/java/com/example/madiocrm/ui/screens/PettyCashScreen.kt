package com.example.madiocrm.ui.screens

import android.widget.Toast
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.madiocrm.data.model.PettyCashEntry
import com.example.madiocrm.data.model.ProjectWallet
import com.example.madiocrm.data.repository.CrmRepository
import com.example.madiocrm.ui.components.AddPettyCashDialog
import com.example.madiocrm.ui.components.formatInr
import com.example.madiocrm.ui.theme.*

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PettyCashScreen(
    repository: CrmRepository,
    onNavigateToProjects: () -> Unit = {},
    modifier: Modifier = Modifier
) {
    val pettyCash by repository.pettyCash.collectAsState()
    val wallets by repository.projectWallets.collectAsState()
    val context = LocalContext.current

    var selectedTab by remember { mutableIntStateOf(0) } // 0: Cash Ledger, 1: Site Wallets
    var selectedFilterType by remember { mutableStateOf("ALL") } // ALL, OUT, IN
    var searchQuery by remember { mutableStateOf("") }
    var showAddVoucherDialog by remember { mutableStateOf(false) }

    val totalCashIn = pettyCash.filter { it.type == "IN" }.sumOf { it.amount }
    val totalCashOut = pettyCash.filter { it.type == "OUT" }.sumOf { it.amount }
    val currentBalance = totalCashIn - totalCashOut
    val totalSiteWalletsBalance = wallets.sumOf { it.balance }

    val filteredEntries = remember(pettyCash, selectedFilterType, searchQuery) {
        pettyCash.filter { entry ->
            val matchesType = when (selectedFilterType) {
                "IN" -> entry.type == "IN"
                "OUT" -> entry.type == "OUT"
                else -> true
            }
            val matchesSearch = searchQuery.isBlank() ||
                    entry.description.contains(searchQuery, ignoreCase = true) ||
                    entry.party.contains(searchQuery, ignoreCase = true) ||
                    entry.category.contains(searchQuery, ignoreCase = true)
            matchesType && matchesSearch
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text(
                            "Petty Cash & Site Cashbook",
                            fontWeight = FontWeight.Bold,
                            style = MaterialTheme.typography.titleLarge
                        )
                        Text(
                            "Balance: ${formatInr(currentBalance)} • ${wallets.size} Site Wallets Active",
                            style = MaterialTheme.typography.bodySmall,
                            color = Slate500
                        )
                    }
                },
                actions = {
                    IconButton(
                        onClick = { showAddVoucherDialog = true },
                        modifier = Modifier.testTag("action_add_petty_cash")
                    ) {
                        Icon(Icons.Default.AddCircle, contentDescription = "Add Voucher", tint = AuraBlue)
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = Color.White)
            )
        },
        floatingActionButton = {
            ExtendedFloatingActionButton(
                onClick = { showAddVoucherDialog = true },
                containerColor = AuraBlue,
                contentColor = Color.White,
                shape = RoundedCornerShape(16.dp),
                icon = { Icon(Icons.Default.Add, contentDescription = null) },
                text = { Text("Record Voucher", fontWeight = FontWeight.Bold) },
                modifier = Modifier.testTag("fab_add_petty_cash")
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
            // Summary Cards
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
                        Text("Available Cash", style = MaterialTheme.typography.bodySmall, color = Slate500, fontSize = 11.sp)
                        Text(formatInr(currentBalance), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold, color = AuraBlue)
                    }
                }

                Card(
                    colors = CardDefaults.cardColors(containerColor = Color.White),
                    shape = RoundedCornerShape(12.dp),
                    elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
                    modifier = Modifier.weight(1f)
                ) {
                    Column(modifier = Modifier.padding(10.dp)) {
                        Text("Site Wallets", style = MaterialTheme.typography.bodySmall, color = Slate500, fontSize = 11.sp)
                        Text(formatInr(totalSiteWalletsBalance), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold, color = Color(0xFF0D9488))
                    }
                }

                Card(
                    colors = CardDefaults.cardColors(containerColor = Color.White),
                    shape = RoundedCornerShape(12.dp),
                    elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
                    modifier = Modifier.weight(1f)
                ) {
                    Column(modifier = Modifier.padding(10.dp)) {
                        Text("Total Spent", style = MaterialTheme.typography.bodySmall, color = Slate500, fontSize = 11.sp)
                        Text(formatInr(totalCashOut), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold, color = DangerRed)
                    }
                }
            }

            // Tabs
            TabRow(
                selectedTabIndex = selectedTab,
                containerColor = Color.White,
                contentColor = AuraBlue
            ) {
                Tab(
                    selected = selectedTab == 0,
                    onClick = { selectedTab = 0 },
                    text = { Text("Cash Ledger (${pettyCash.size})", fontWeight = FontWeight.SemiBold) },
                    modifier = Modifier.testTag("tab_petty_cash_ledger")
                )
                Tab(
                    selected = selectedTab == 1,
                    onClick = { selectedTab = 1 },
                    text = { Text("Site Wallets (${wallets.size})", fontWeight = FontWeight.SemiBold) },
                    modifier = Modifier.testTag("tab_site_wallets")
                )
            }

            if (selectedTab == 0) {
                // Search & Filter
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp, vertical = 6.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    OutlinedTextField(
                        value = searchQuery,
                        onValueChange = { searchQuery = it },
                        placeholder = { Text("Search party, category...", color = Slate400, fontSize = 12.sp) },
                        leadingIcon = { Icon(Icons.Default.Search, contentDescription = null, tint = Slate400, modifier = Modifier.size(18.dp)) },
                        trailingIcon = {
                            if (searchQuery.isNotEmpty()) {
                                IconButton(onClick = { searchQuery = "" }) {
                                    Icon(Icons.Default.Close, contentDescription = "Clear", tint = Slate400, modifier = Modifier.size(16.dp))
                                }
                            }
                        },
                        shape = RoundedCornerShape(10.dp),
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedContainerColor = Color.White,
                            unfocusedContainerColor = Color.White,
                            focusedBorderColor = AuraBlue,
                            unfocusedBorderColor = Slate200
                        ),
                        singleLine = true,
                        modifier = Modifier
                            .weight(1f)
                            .testTag("input_search_petty_cash")
                    )

                    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        FilterChip(
                            selected = selectedFilterType == "ALL",
                            onClick = { selectedFilterType = "ALL" },
                            label = { Text("All", fontSize = 11.sp) }
                        )
                        FilterChip(
                            selected = selectedFilterType == "OUT",
                            onClick = { selectedFilterType = "OUT" },
                            label = { Text("OUT", fontSize = 11.sp) }
                        )
                        FilterChip(
                            selected = selectedFilterType == "IN",
                            onClick = { selectedFilterType = "IN" },
                            label = { Text("IN", fontSize = 11.sp) }
                        )
                    }
                }

                // Ledger list
                if (filteredEntries.isEmpty()) {
                    Box(
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(32.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Icon(Icons.Default.ReceiptLong, contentDescription = null, tint = Slate300, modifier = Modifier.size(56.dp))
                            Spacer(modifier = Modifier.height(12.dp))
                            Text("No cash vouchers found", style = MaterialTheme.typography.titleMedium, color = Slate600)
                            Spacer(modifier = Modifier.height(6.dp))
                            Text("Record site purchases, labor tips, or top-ups", style = MaterialTheme.typography.bodySmall, color = Slate400)
                        }
                    }
                } else {
                    LazyColumn(
                        modifier = Modifier.fillMaxSize(),
                        contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 4.dp, bottom = 80.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        items(filteredEntries, key = { it.id }) { entry ->
                            PettyCashLedgerCard(entry = entry)
                        }
                    }
                }
            } else {
                // Site Wallets Tab
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 10.dp, bottom = 80.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    items(wallets, key = { it.id }) { wallet ->
                        SiteWalletDetailCard(
                            wallet = wallet,
                            onTopUp = {
                                showAddVoucherDialog = true
                            },
                            onViewProject = {
                                onNavigateToProjects()
                            }
                        )
                    }
                }
            }
        }
    }

    if (showAddVoucherDialog) {
        AddPettyCashDialog(
            onDismiss = { showAddVoucherDialog = false },
            onSave = { voucher ->
                repository.addPettyCash(voucher)
                showAddVoucherDialog = false
                Toast.makeText(context, "Voucher #${voucher.id} recorded successfully!", Toast.LENGTH_SHORT).show()
            }
        )
    }
}

@Composable
fun PettyCashLedgerCard(entry: PettyCashEntry, modifier: Modifier = Modifier) {
    val isIncome = entry.type == "IN"

    Card(
        colors = CardDefaults.cardColors(containerColor = Color.White),
        shape = RoundedCornerShape(14.dp),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
        modifier = modifier.fillMaxWidth()
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(14.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Surface(
                        color = if (isIncome) SuccessGreenLight else DangerRedLight,
                        shape = RoundedCornerShape(6.dp)
                    ) {
                        Text(
                            entry.type,
                            color = if (isIncome) SuccessGreen else DangerRed,
                            fontWeight = FontWeight.Bold,
                            style = MaterialTheme.typography.labelSmall,
                            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                        )
                    }
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(
                        entry.category,
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.Bold,
                        color = Slate800
                    )
                }
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = "${entry.party} • ${entry.description}",
                    style = MaterialTheme.typography.bodySmall,
                    color = Slate600,
                    maxLines = 1
                )
                Text(
                    text = "${entry.id} • ${entry.date}",
                    style = MaterialTheme.typography.bodySmall,
                    color = Slate400,
                    fontSize = 10.sp
                )
            }

            Text(
                text = (if (isIncome) "+ " else "- ") + formatInr(entry.amount),
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                color = if (isIncome) SuccessGreen else DangerRed
            )
        }
    }
}

@Composable
fun SiteWalletDetailCard(
    wallet: ProjectWallet,
    onTopUp: () -> Unit,
    onViewProject: () -> Unit,
    modifier: Modifier = Modifier
) {
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
                    Text(
                        text = wallet.projectName,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        color = Slate900
                    )
                    Text(
                        text = "Site Engineer: ${wallet.engineerName}",
                        style = MaterialTheme.typography.bodySmall,
                        color = Slate500
                    )
                }

                Surface(
                    color = if (wallet.balance < 5000) WarningAmberLight else Color(0xFFE8F8F0),
                    shape = RoundedCornerShape(8.dp)
                ) {
                    Text(
                        text = if (wallet.balance < 5000) "Low Balance" else "Funded",
                        color = if (wallet.balance < 5000) Color(0xFFB45309) else SuccessGreen,
                        fontSize = 11.sp,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                    )
                }
            }

            Spacer(modifier = Modifier.height(12.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Column {
                    Text("Allocated Budget", style = MaterialTheme.typography.bodySmall, color = Slate400, fontSize = 10.sp)
                    Text(formatInr(wallet.totalAllocated), style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold, color = Slate800)
                }
                Column {
                    Text("Total Spent", style = MaterialTheme.typography.bodySmall, color = Slate400, fontSize = 10.sp)
                    Text(formatInr(wallet.totalSpent), style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold, color = DangerRed)
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text("Wallet Balance", style = MaterialTheme.typography.bodySmall, color = Slate400, fontSize = 10.sp)
                    Text(formatInr(wallet.balance), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = AuraBlue)
                }
            }

            Spacer(modifier = Modifier.height(12.dp))
            HorizontalDivider(color = Slate100)
            Spacer(modifier = Modifier.height(10.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                TextButton(
                    onClick = onViewProject,
                    contentPadding = PaddingValues(0.dp)
                ) {
                    Text("View Site Execution ➔", fontSize = 12.sp, color = AuraBlue, fontWeight = FontWeight.SemiBold)
                }

                Button(
                    onClick = onTopUp,
                    shape = RoundedCornerShape(8.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = AuraBlue),
                    contentPadding = PaddingValues(horizontal = 12.dp, vertical = 6.dp)
                ) {
                    Icon(Icons.Default.Add, contentDescription = null, modifier = Modifier.size(14.dp))
                    Spacer(modifier = Modifier.width(4.dp))
                    Text("Top-up Wallet", fontSize = 11.sp, fontWeight = FontWeight.Bold)
                }
            }
        }
    }
}

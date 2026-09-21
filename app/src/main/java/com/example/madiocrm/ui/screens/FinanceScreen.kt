package com.example.madiocrm.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.ReceiptLong
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.madiocrm.data.model.PettyCashEntry
import com.example.madiocrm.data.model.TaxInvoice
import com.example.madiocrm.data.repository.CrmRepository
import com.example.madiocrm.ui.components.AddPettyCashDialog
import com.example.madiocrm.ui.components.formatInr
import com.example.madiocrm.ui.theme.*

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FinanceScreen(
    repository: CrmRepository,
    modifier: Modifier = Modifier
) {
    val invoices by repository.invoices.collectAsState()
    val pettyCash by repository.pettyCash.collectAsState()

    var selectedTab by remember { mutableStateOf(0) } // 0: Tax Invoices, 1: Petty Cash
    var showAddVoucherDialog by remember { mutableStateOf(false) }

    val totalCashIn = pettyCash.filter { it.type == "IN" }.sumOf { it.amount }
    val totalCashOut = pettyCash.filter { it.type == "OUT" }.sumOf { it.amount }
    val currentCashBalance = totalCashIn - totalCashOut

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text("Finance & Cashbook", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleLarge)
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = Color.White)
            )
        },
        floatingActionButton = {
            if (selectedTab == 1) {
                FloatingActionButton(
                    onClick = { showAddVoucherDialog = true },
                    containerColor = AuraBlue,
                    contentColor = Color.White,
                    shape = CircleShape,
                    modifier = Modifier
                        .padding(bottom = 60.dp)
                        .testTag("petty_cash_fab_add")
                ) {
                    Icon(Icons.Default.Add, contentDescription = "New Voucher")
                }
            }
        }
    ) { innerPadding ->
        Column(
            modifier = modifier
                .fillMaxSize()
                .background(Slate50)
                .padding(innerPadding)
        ) {
            TabRow(
                selectedTabIndex = selectedTab,
                containerColor = Color.White,
                contentColor = AuraBlue
            ) {
                Tab(
                    selected = selectedTab == 0,
                    onClick = { selectedTab = 0 },
                    text = { Text("Tax Invoices (${invoices.size})", fontWeight = FontWeight.SemiBold) },
                    modifier = Modifier.testTag("tab_invoices")
                )
                Tab(
                    selected = selectedTab == 1,
                    onClick = { selectedTab = 1 },
                    text = { Text("Petty Cashbook", fontWeight = FontWeight.SemiBold) },
                    modifier = Modifier.testTag("tab_petty_cash")
                )
            }

            if (selectedTab == 0) {
                // Invoices List
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(16.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    items(invoices, key = { it.id }) { invoice ->
                        InvoiceCard(invoice = invoice)
                    }
                }
            } else {
                // Petty Cashbook Ledger
                Column(modifier = Modifier.fillMaxSize()) {
                    // Balance Snapshot
                    Card(
                        colors = CardDefaults.cardColors(containerColor = Color.White),
                        shape = RoundedCornerShape(16.dp),
                        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 16.dp, vertical = 12.dp)
                    ) {
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(16.dp),
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Column {
                                Text("Cash IN", style = MaterialTheme.typography.bodySmall, color = Slate500)
                                Text(formatInr(totalCashIn), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = SuccessGreen)
                            }
                            Column {
                                Text("Expenses (OUT)", style = MaterialTheme.typography.bodySmall, color = Slate500)
                                Text(formatInr(totalCashOut), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = DangerRed)
                            }
                            Column {
                                Text("Cashbox Balance", style = MaterialTheme.typography.bodySmall, color = Slate500)
                                Text(formatInr(currentCashBalance), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = AuraBlue)
                            }
                        }
                    }

                    LazyColumn(
                        modifier = Modifier.fillMaxSize(),
                        contentPadding = PaddingValues(start = 16.dp, end = 16.dp, bottom = 80.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        items(pettyCash, key = { it.id }) { entry ->
                            PettyCashCard(entry = entry)
                        }
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
            }
        )
    }
}

@Composable
fun InvoiceCard(invoice: TaxInvoice, modifier: Modifier = Modifier) {
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
                Column {
                    Text(invoice.invoiceNo, style = MaterialTheme.typography.labelLarge, color = AuraBlue, fontWeight = FontWeight.Bold)
                    Text(invoice.customerName, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = Slate900)
                }
                Surface(
                    color = if (invoice.status == "Paid") SuccessGreenLight else WarningAmberLight,
                    shape = RoundedCornerShape(10.dp)
                ) {
                    Text(
                        invoice.status,
                        color = if (invoice.status == "Paid") SuccessGreen else Color(0xFFB45309),
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                    )
                }
            }

            Spacer(modifier = Modifier.height(8.dp))
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("Date: ${invoice.date}", style = MaterialTheme.typography.bodySmall, color = Slate500)
                Text("GST Slab: ${invoice.gstRate.toInt()}%", style = MaterialTheme.typography.bodySmall, color = Slate500)
            }

            Spacer(modifier = Modifier.height(8.dp))
            HorizontalDivider(color = Slate100)
            Spacer(modifier = Modifier.height(8.dp))

            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Column {
                    Text("Total Invoice", style = MaterialTheme.typography.labelMedium, color = Slate400, fontSize = 10.sp)
                    Text(formatInr(invoice.totalAmount), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = Slate900)
                }
                Column {
                    Text("Paid", style = MaterialTheme.typography.labelMedium, color = Slate400, fontSize = 10.sp)
                    Text(formatInr(invoice.paidAmount), style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold, color = SuccessGreen)
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text("Balance", style = MaterialTheme.typography.labelMedium, color = Slate400, fontSize = 10.sp)
                    Text(formatInr(invoice.balance), style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.Bold, color = if (invoice.balance > 0) DangerRed else Slate400)
                }
            }
        }
    }
}

@Composable
fun PettyCashCard(entry: PettyCashEntry, modifier: Modifier = Modifier) {
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
                        color = if (entry.type == "IN") SuccessGreenLight else DangerRedLight,
                        shape = RoundedCornerShape(6.dp)
                    ) {
                        Text(
                            entry.type,
                            color = if (entry.type == "IN") SuccessGreen else DangerRed,
                            fontWeight = FontWeight.Bold,
                            style = MaterialTheme.typography.labelSmall,
                            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                        )
                    }
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(entry.category, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold, color = Slate800)
                }
                Spacer(modifier = Modifier.height(3.dp))
                Text(
                    text = "${entry.party}  |  ${entry.description}",
                    style = MaterialTheme.typography.bodySmall,
                    color = Slate600,
                    maxLines = 1
                )
                Text(entry.date, style = MaterialTheme.typography.bodySmall, color = Slate400, fontSize = 10.sp)
            }

            Text(
                text = (if (entry.type == "IN") "+ " else "- ") + formatInr(entry.amount),
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                color = if (entry.type == "IN") SuccessGreen else DangerRed
            )
        }
    }
}

package com.example.madiocrm.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Payment
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.madiocrm.data.model.Division
import com.example.madiocrm.data.model.SaleOrder
import com.example.madiocrm.data.model.SaleStatus
import com.example.madiocrm.data.repository.CrmRepository
import com.example.madiocrm.ui.components.DivisionBadge
import com.example.madiocrm.ui.components.DivisionFilterRow
import com.example.madiocrm.ui.components.formatInr
import com.example.madiocrm.ui.theme.*

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SalesScreen(
    repository: CrmRepository,
    modifier: Modifier = Modifier
) {
    val sales by repository.sales.collectAsState()
    var selectedDivision by remember { mutableStateOf(Division.ALL) }
    var selectedSaleForPayment by remember { mutableStateOf<SaleOrder?>(null) }

    val filteredSales = remember(sales, selectedDivision) {
        if (selectedDivision == Division.ALL) sales else sales.filter { it.division == selectedDivision }
    }

    val totalSales = filteredSales.sumOf { it.totalValue }
    val totalCollected = filteredSales.sumOf { it.paidAmount }
    val totalBalance = totalSales - totalCollected

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text("Sales Register", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleLarge)
                        Text("Total Bookings: ${formatInr(totalSales)}", style = MaterialTheme.typography.bodySmall, color = Slate500)
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = Color.White)
            )
        }
    ) { innerPadding ->
        Column(
            modifier = modifier
                .fillMaxSize()
                .background(Slate50)
                .padding(innerPadding)
        ) {
            // Revenue Summary
            Card(
                colors = CardDefaults.cardColors(containerColor = Color.White),
                shape = RoundedCornerShape(16.dp),
                elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 8.dp)
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(16.dp),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Column {
                        Text("Booked Orders", style = MaterialTheme.typography.bodySmall, color = Slate500)
                        Text(formatInr(totalSales), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = Slate900)
                    }
                    Column {
                        Text("Collected", style = MaterialTheme.typography.bodySmall, color = Slate500)
                        Text(formatInr(totalCollected), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = SuccessGreen)
                    }
                    Column {
                        Text("Balance Due", style = MaterialTheme.typography.bodySmall, color = Slate500)
                        Text(formatInr(totalBalance), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = WarningAmber)
                    }
                }
            }

            DivisionFilterRow(
                selectedDivision = selectedDivision,
                onSelect = { selectedDivision = it }
            )

            LazyColumn(
                modifier = Modifier.fillMaxSize(),
                contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 8.dp, bottom = 80.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                items(filteredSales, key = { it.id }) { sale ->
                    SaleOrderCard(
                        sale = sale,
                        onRecordPayment = { selectedSaleForPayment = sale }
                    )
                }
            }
        }
    }

    // Payment Dialog
    selectedSaleForPayment?.let { sale ->
        RecordPaymentDialog(
            sale = sale,
            onDismiss = { selectedSaleForPayment = null },
            onConfirm = { amount ->
                repository.recordPayment(sale.id, amount)
                selectedSaleForPayment = null
            }
        )
    }
}

@Composable
fun SaleOrderCard(
    sale: SaleOrder,
    onRecordPayment: () -> Unit,
    modifier: Modifier = Modifier
) {
    val progress = (sale.paidAmount / sale.totalValue.coerceAtLeast(1.0)).toFloat().coerceIn(0f, 1f)

    Card(
        colors = CardDefaults.cardColors(containerColor = Color.White),
        shape = RoundedCornerShape(16.dp),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
        modifier = modifier
            .fillMaxWidth()
            .testTag("sale_order_card_${sale.id}")
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(sale.saleNo, style = MaterialTheme.typography.labelLarge, color = AuraBlue, fontWeight = FontWeight.Bold)
                        Spacer(modifier = Modifier.width(6.dp))
                        DivisionBadge(sale.division)
                    }
                    Text(sale.customerName, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = Slate900)
                }

                val (badgeBg, badgeFg) = when (sale.status) {
                    SaleStatus.PAID -> SuccessGreenLight to SuccessGreen
                    SaleStatus.PARTIAL -> WarningAmberLight to Color(0xFFB45309)
                    SaleStatus.PENDING -> DangerRedLight to DangerRed
                }
                Surface(
                    color = badgeBg,
                    shape = RoundedCornerShape(12.dp)
                ) {
                    Text(
                        sale.status.displayName,
                        color = badgeFg,
                        fontWeight = FontWeight.Bold,
                        style = MaterialTheme.typography.labelMedium,
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                    )
                }
            }

            if (sale.remarks.isNotBlank()) {
                Spacer(modifier = Modifier.height(6.dp))
                Text(sale.remarks, style = MaterialTheme.typography.bodySmall, color = Slate600)
            }

            Spacer(modifier = Modifier.height(10.dp))

            // Payment Progress
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Text("Collected: ${formatInr(sale.paidAmount)}", style = MaterialTheme.typography.bodySmall, color = Slate600)
                Text("Total: ${formatInr(sale.totalValue)}", style = MaterialTheme.typography.bodySmall, fontWeight = FontWeight.SemiBold, color = Slate900)
            }
            Spacer(modifier = Modifier.height(4.dp))
            LinearProgressIndicator(
                progress = { progress },
                modifier = Modifier
                    .fillMaxWidth()
                    .height(6.dp)
                    .clip(RoundedCornerShape(3.dp)),
                color = if (sale.status == SaleStatus.PAID) SuccessGreen else AuraBlue,
                trackColor = Slate200
            )

            Spacer(modifier = Modifier.height(10.dp))
            HorizontalDivider(color = Slate100)
            Spacer(modifier = Modifier.height(8.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column {
                    Text("Delivery Target", style = MaterialTheme.typography.labelMedium, color = Slate400, fontSize = 10.sp)
                    Text(sale.deliveryDate, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.Medium, color = Slate800)
                }

                if (sale.status != SaleStatus.PAID) {
                    Button(
                        onClick = onRecordPayment,
                        colors = ButtonDefaults.buttonColors(containerColor = AuraBlue),
                        shape = RoundedCornerShape(10.dp),
                        contentPadding = PaddingValues(horizontal = 12.dp, vertical = 6.dp),
                        modifier = Modifier.testTag("record_payment_button_${sale.id}")
                    ) {
                        Icon(Icons.Default.Payment, contentDescription = null, modifier = Modifier.size(16.dp))
                        Spacer(modifier = Modifier.width(4.dp))
                        Text("Record Payment", fontSize = 12.sp)
                    }
                }
            }
        }
    }
}

@Composable
fun RecordPaymentDialog(
    sale: SaleOrder,
    onDismiss: () -> Unit,
    onConfirm: (Double) -> Unit
) {
    var amountText by remember { mutableStateOf("") }
    val remainingBalance = sale.balanceDue

    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            Column {
                Text("Record Payment Receipt", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium, color = AuraBlue)
                Text("For ${sale.customerName} (${sale.saleNo})", style = MaterialTheme.typography.bodySmall, color = Slate600)
            }
        },
        text = {
            Column {
                Text("Current Balance Due: ${formatInr(remainingBalance)}", style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold, color = DangerRed)
                Spacer(modifier = Modifier.height(12.dp))
                OutlinedTextField(
                    value = amountText,
                    onValueChange = { amountText = it },
                    label = { Text("Payment Received (₹) *") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )
                Spacer(modifier = Modifier.height(8.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(
                        onClick = { amountText = remainingBalance.toInt().toString() }
                    ) {
                        Text("Pay Full Balance", fontSize = 11.sp)
                    }
                }
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    val amt = amountText.toDoubleOrNull() ?: 0.0
                    if (amt > 0) {
                        onConfirm(amt)
                    }
                },
                colors = ButtonDefaults.buttonColors(containerColor = SuccessGreen)
            ) {
                Text("Confirm Receipt")
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("Cancel")
            }
        }
    )
}

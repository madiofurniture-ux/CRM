package com.example.madiocrm.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.madiocrm.data.model.Division
import com.example.madiocrm.data.model.InventoryItem
import com.example.madiocrm.data.repository.CrmRepository
import com.example.madiocrm.ui.components.DivisionBadge
import com.example.madiocrm.ui.components.DivisionFilterRow
import com.example.madiocrm.ui.components.formatInr
import com.example.madiocrm.ui.theme.*

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun InventoryScreen(
    repository: CrmRepository,
    modifier: Modifier = Modifier
) {
    val inventory by repository.inventory.collectAsState()
    val isCostMasked by repository.isCostMasked.collectAsState()

    var searchQuery by remember { mutableStateOf("") }
    var selectedDivision by remember { mutableStateOf(Division.ALL) }

    val filteredItems = remember(inventory, searchQuery, selectedDivision) {
        inventory.filter { item ->
            val matchesDivision = selectedDivision == Division.ALL || item.division == selectedDivision
            val matchesSearch = searchQuery.isBlank() ||
                    item.name.contains(searchQuery, ignoreCase = true) ||
                    item.sku.contains(searchQuery, ignoreCase = true) ||
                    item.category.contains(searchQuery, ignoreCase = true) ||
                    item.vendor.contains(searchQuery, ignoreCase = true)
            matchesDivision && matchesSearch
        }
    }

    val totalSkus = filteredItems.size
    val totalPieces = filteredItems.sumOf { it.qty }
    val lowStockCount = filteredItems.count { it.status == "Low Stock" || it.qty <= 2 }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text("Inventory & Warehouse", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleLarge)
                        Text("$totalSkus SKUs | $totalPieces Units", style = MaterialTheme.typography.bodySmall, color = Slate500)
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = Color.White),
                actions = {
                    // Privacy Masking Toggle for Cost Price & Margin
                    IconButton(
                        onClick = { repository.toggleCostMask() },
                        modifier = Modifier.testTag("cost_mask_toggle")
                    ) {
                        Icon(
                            imageVector = if (isCostMasked) Icons.Default.VisibilityOff else Icons.Default.Visibility,
                            contentDescription = "Toggle Cost Privacy",
                            tint = if (isCostMasked) Slate500 else AuraBlue
                        )
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
            // Search Input
            OutlinedTextField(
                value = searchQuery,
                onValueChange = { searchQuery = it },
                placeholder = { Text("Search SKU, item name, vendor...") },
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
                    .testTag("inventory_search_input")
            )

            DivisionFilterRow(
                selectedDivision = selectedDivision,
                onSelect = { selectedDivision = it }
            )

            // Low Stock Warning Banner if any
            if (lowStockCount > 0) {
                Surface(
                    color = WarningAmberLight,
                    shape = RoundedCornerShape(12.dp),
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp, vertical = 4.dp)
                ) {
                    Row(
                        modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(Icons.Default.WarningAmber, contentDescription = null, tint = Color(0xFFB45309), modifier = Modifier.size(18.dp))
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(
                            "$lowStockCount items are running low on stock",
                            style = MaterialTheme.typography.bodySmall,
                            fontWeight = FontWeight.Medium,
                            color = Color(0xFFB45309)
                        )
                    }
                }
            }

            LazyColumn(
                modifier = Modifier.fillMaxSize(),
                contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 8.dp, bottom = 80.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                items(filteredItems, key = { it.id }) { item ->
                    InventoryItemCard(
                        item = item,
                        isCostMasked = isCostMasked,
                        onAdjustQty = { delta ->
                            repository.updateInventoryQty(item.id, delta)
                        }
                    )
                }
            }
        }
    }
}

@Composable
fun InventoryItemCard(
    item: InventoryItem,
    isCostMasked: Boolean,
    onAdjustQty: (Int) -> Unit,
    modifier: Modifier = Modifier
) {
    Card(
        colors = CardDefaults.cardColors(containerColor = Color.White),
        shape = RoundedCornerShape(16.dp),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
        modifier = modifier
            .fillMaxWidth()
            .testTag("inventory_card_${item.id}")
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(item.sku, style = MaterialTheme.typography.labelLarge, color = AuraBlue, fontWeight = FontWeight.Bold)
                        Spacer(modifier = Modifier.width(6.dp))
                        DivisionBadge(item.division)
                        Spacer(modifier = Modifier.width(6.dp))
                        Surface(
                            color = Slate100,
                            shape = RoundedCornerShape(4.dp)
                        ) {
                            Text(
                                item.category,
                                style = MaterialTheme.typography.labelSmall,
                                color = Slate600,
                                modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                            )
                        }
                    }
                    Spacer(modifier = Modifier.height(2.dp))
                    Text(item.name, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = Slate900)
                }

                Surface(
                    color = if (item.status == "Low Stock" || item.qty <= 2) WarningAmberLight else SuccessGreenLight,
                    shape = RoundedCornerShape(10.dp)
                ) {
                    Text(
                        item.status,
                        color = if (item.status == "Low Stock" || item.qty <= 2) Color(0xFFB45309) else SuccessGreen,
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                    )
                }
            }

            Spacer(modifier = Modifier.height(6.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Text("Vendor: ${item.vendor}", style = MaterialTheme.typography.bodySmall, color = Slate500)
                Text("Location: ${item.location}", style = MaterialTheme.typography.bodySmall, color = Slate500)
            }

            Spacer(modifier = Modifier.height(10.dp))
            HorizontalDivider(color = Slate100)
            Spacer(modifier = Modifier.height(8.dp))

            // Pricing & Quantity Controls
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column {
                    Text("MRP (Sell Price)", style = MaterialTheme.typography.labelMedium, color = Slate400, fontSize = 10.sp)
                    Text(formatInr(item.mrp), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = Slate900)
                }

                Column {
                    Text("Cost / Margin", style = MaterialTheme.typography.labelMedium, color = Slate400, fontSize = 10.sp)
                    if (isCostMasked) {
                        Text("••••••", style = MaterialTheme.typography.bodyMedium, color = Slate400, fontWeight = FontWeight.Bold)
                    } else {
                        Text("${formatInr(item.costPrice)} (${item.marginPct}%)", style = MaterialTheme.typography.bodyMedium, color = AuraBlue, fontWeight = FontWeight.SemiBold)
                    }
                }

                // Quantity Adjuster (+/-)
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(4.dp)
                ) {
                    FilledTonalIconButton(
                        onClick = { onAdjustQty(-1) },
                        colors = IconButtonDefaults.filledTonalIconButtonColors(containerColor = Slate100),
                        modifier = Modifier
                            .size(32.dp)
                            .testTag("qty_minus_${item.id}")
                    ) {
                        Icon(Icons.Default.Remove, contentDescription = "Decrease", tint = Slate700, modifier = Modifier.size(16.dp))
                    }
                    Text(
                        "${item.qty}",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        color = Slate900,
                        modifier = Modifier.padding(horizontal = 6.dp)
                    )
                    FilledTonalIconButton(
                        onClick = { onAdjustQty(1) },
                        colors = IconButtonDefaults.filledTonalIconButtonColors(containerColor = Slate100),
                        modifier = Modifier
                            .size(32.dp)
                            .testTag("qty_plus_${item.id}")
                    ) {
                        Icon(Icons.Default.Add, contentDescription = "Increase", tint = Slate700, modifier = Modifier.size(16.dp))
                    }
                }
            }
        }
    }
}

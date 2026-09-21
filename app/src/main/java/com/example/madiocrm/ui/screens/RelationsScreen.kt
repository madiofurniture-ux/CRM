package com.example.madiocrm.ui.screens

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Chat
import androidx.compose.material.icons.filled.Phone
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.madiocrm.data.model.Architect
import com.example.madiocrm.data.model.Customer
import com.example.madiocrm.data.repository.CrmRepository
import com.example.madiocrm.ui.components.DivisionBadge
import com.example.madiocrm.ui.components.formatInr
import com.example.madiocrm.ui.theme.*

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RelationsScreen(
    repository: CrmRepository,
    modifier: Modifier = Modifier
) {
    val customers by repository.customers.collectAsState()
    val architects by repository.architects.collectAsState()
    val context = LocalContext.current

    var selectedTab by remember { mutableStateOf(0) } // 0: Customers, 1: Architects

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text("Relations & Network", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleLarge)
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
            TabRow(
                selectedTabIndex = selectedTab,
                containerColor = Color.White,
                contentColor = AuraBlue
            ) {
                Tab(
                    selected = selectedTab == 0,
                    onClick = { selectedTab = 0 },
                    text = { Text("Clients (${customers.size})", fontWeight = FontWeight.SemiBold) }
                )
                Tab(
                    selected = selectedTab == 1,
                    onClick = { selectedTab = 1 },
                    text = { Text("Architects (${architects.size})", fontWeight = FontWeight.SemiBold) }
                )
            }

            if (selectedTab == 0) {
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(16.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    items(customers, key = { it.id }) { customer ->
                        CustomerCard(
                            customer = customer,
                            onCall = {
                                val intent = Intent(Intent.ACTION_DIAL, Uri.parse("tel:${customer.phone}"))
                                context.startActivity(intent)
                            }
                        )
                    }
                }
            } else {
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(16.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    items(architects, key = { it.id }) { architect ->
                        ArchitectCard(
                            architect = architect,
                            onCall = {
                                val intent = Intent(Intent.ACTION_DIAL, Uri.parse("tel:${architect.phone}"))
                                context.startActivity(intent)
                            },
                            onWhatsApp = {
                                val cleanPhone = architect.phone.replace("[^0-9]".toRegex(), "")
                                val intent = Intent(Intent.ACTION_VIEW, Uri.parse("https://wa.me/$cleanPhone"))
                                context.startActivity(intent)
                            }
                        )
                    }
                }
            }
        }
    }
}

@Composable
fun CustomerCard(customer: Customer, onCall: () -> Unit, modifier: Modifier = Modifier) {
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
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(customer.name, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = Slate900)
                        Spacer(modifier = Modifier.width(6.dp))
                        DivisionBadge(customer.division)
                    }
                    Text(customer.phone, style = MaterialTheme.typography.bodySmall, color = Slate500)
                }
                IconButton(onClick = onCall) {
                    Icon(Icons.Default.Phone, contentDescription = "Call", tint = AuraBlue)
                }
            }

            if (customer.address.isNotBlank()) {
                Spacer(modifier = Modifier.height(4.dp))
                Text(customer.address, style = MaterialTheme.typography.bodySmall, color = Slate600)
            }

            Spacer(modifier = Modifier.height(8.dp))
            HorizontalDivider(color = Slate100)
            Spacer(modifier = Modifier.height(8.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Column {
                    Text("Lifetime Value", style = MaterialTheme.typography.labelMedium, color = Slate400, fontSize = 10.sp)
                    Text(formatInr(customer.lifetimeValue), style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.Bold, color = AuraBlue)
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text("Orders", style = MaterialTheme.typography.labelMedium, color = Slate400, fontSize = 10.sp)
                    Text("${customer.totalOrders} Completed", style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold, color = Slate700)
                }
            }
        }
    }
}

@Composable
fun ArchitectCard(
    architect: Architect,
    onCall: () -> Unit,
    onWhatsApp: () -> Unit,
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
                    Text(architect.name, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = Slate900)
                    Text(architect.firm, style = MaterialTheme.typography.bodySmall, color = AuraBlue, fontWeight = FontWeight.Medium)
                    Text(architect.location, style = MaterialTheme.typography.bodySmall, color = Slate500)
                }
                Row {
                    FilledTonalIconButton(
                        onClick = onCall,
                        colors = IconButtonDefaults.filledTonalIconButtonColors(containerColor = Slate100),
                        modifier = Modifier.size(36.dp)
                    ) {
                        Icon(Icons.Default.Phone, contentDescription = "Call", tint = AuraBlue, modifier = Modifier.size(18.dp))
                    }
                    Spacer(modifier = Modifier.width(6.dp))
                    FilledTonalIconButton(
                        onClick = onWhatsApp,
                        colors = IconButtonDefaults.filledTonalIconButtonColors(containerColor = SuccessGreenLight),
                        modifier = Modifier.size(36.dp)
                    ) {
                        Icon(Icons.Default.Chat, contentDescription = "WhatsApp", tint = SuccessGreen, modifier = Modifier.size(18.dp))
                    }
                }
            }

            Spacer(modifier = Modifier.height(10.dp))
            HorizontalDivider(color = Slate100)
            Spacer(modifier = Modifier.height(8.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Column {
                    Text("Referred Projects", style = MaterialTheme.typography.labelMedium, color = Slate400, fontSize = 10.sp)
                    Text("${architect.projectsReferred} Deals", style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.Bold, color = Slate900)
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text("Commission Rate", style = MaterialTheme.typography.labelMedium, color = Slate400, fontSize = 10.sp)
                    Text("${architect.commissionRate}% Payout", style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.Bold, color = GoldAccent)
                }
            }
        }
    }
}

package com.example.madiocrm.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import com.example.madiocrm.data.model.*
import com.example.madiocrm.data.repository.CrmRepository
import com.example.madiocrm.ui.theme.*
import java.util.UUID

@Composable
fun AddLeadDialog(
    onDismiss: () -> Unit,
    onSave: (Lead) -> Unit
) {
    var name by remember { mutableStateOf("") }
    var phone by remember { mutableStateOf("") }
    var source by remember { mutableStateOf("Walk-in") }
    var division by remember { mutableStateOf(Division.FURNITURE) }
    var estimatedValue by remember { mutableStateOf("") }
    var remarks by remember { mutableStateOf("") }
    var followUpDate by remember { mutableStateOf("2026-09-24") }
    var confidenceLevel by remember { mutableStateOf(70) }

    Dialog(onDismissRequest = onDismiss) {
        Card(
            shape = RoundedCornerShape(20.dp),
            colors = CardDefaults.cardColors(containerColor = Color.White),
            modifier = Modifier
                .fillMaxWidth()
                .padding(vertical = 16.dp)
        ) {
            Column(
                modifier = Modifier
                    .padding(20.dp)
                    .verticalScroll(rememberScrollState())
            ) {
                Text(
                    text = "New Sales Lead",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = AuraBlue
                )
                Text(
                    text = "Capture prospect requirements across MADIO divisions",
                    style = MaterialTheme.typography.bodySmall,
                    color = Slate600
                )

                Spacer(modifier = Modifier.height(16.dp))

                OutlinedTextField(
                    value = name,
                    onValueChange = { name = it },
                    label = { Text("Customer Name *") },
                    modifier = Modifier
                        .fillMaxWidth()
                        .testTag("lead_input_name"),
                    singleLine = true
                )

                Spacer(modifier = Modifier.height(10.dp))

                OutlinedTextField(
                    value = phone,
                    onValueChange = { phone = it },
                    label = { Text("Phone Number *") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
                    modifier = Modifier
                        .fillMaxWidth()
                        .testTag("lead_input_phone"),
                    singleLine = true
                )

                Spacer(modifier = Modifier.height(12.dp))
                Text("Division", style = MaterialTheme.typography.labelMedium, color = Slate700)
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    listOf(Division.FURNITURE, Division.MAP, Division.DW).forEach { div ->
                        FilterChip(
                            selected = division == div,
                            onClick = { division = div },
                            label = { Text(div.shortCode) }
                        )
                    }
                }

                Spacer(modifier = Modifier.height(10.dp))

                OutlinedTextField(
                    value = source,
                    onValueChange = { source = it },
                    label = { Text("Lead Source (Instagram, Architect, Walk-in)") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )

                Spacer(modifier = Modifier.height(10.dp))

                OutlinedTextField(
                    value = estimatedValue,
                    onValueChange = { estimatedValue = it },
                    label = { Text("Estimated Deal Value (₹)") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )

                Spacer(modifier = Modifier.height(10.dp))

                OutlinedTextField(
                    value = followUpDate,
                    onValueChange = { followUpDate = it },
                    label = { Text("Follow-up Target Date") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )

                Spacer(modifier = Modifier.height(10.dp))

                OutlinedTextField(
                    value = remarks,
                    onValueChange = { remarks = it },
                    label = { Text("Requirement Details & Notes") },
                    modifier = Modifier.fillMaxWidth(),
                    maxLines = 3
                )

                Spacer(modifier = Modifier.height(18.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.End,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    TextButton(onClick = onDismiss) {
                        Text("Cancel", color = Slate600)
                    }
                    Spacer(modifier = Modifier.width(8.dp))
                    Button(
                        onClick = {
                            if (name.isNotBlank() && phone.isNotBlank()) {
                                onSave(
                                    Lead(
                                        id = "LD-" + System.currentTimeMillis().toString().takeLast(4),
                                        name = name.trim(),
                                        phone = phone.trim(),
                                        source = source.ifBlank { "Direct" },
                                        division = division,
                                        stage = LeadStage.NEW,
                                        followUpDate = followUpDate,
                                        remarks = remarks,
                                        estimatedValue = estimatedValue.toDoubleOrNull() ?: 0.0,
                                        confidenceLevel = confidenceLevel,
                                        createdAt = "Today"
                                    )
                                )
                            }
                        },
                        colors = ButtonDefaults.buttonColors(containerColor = AuraBlue),
                        modifier = Modifier.testTag("save_lead_button")
                    ) {
                        Text("Create Lead")
                    }
                }
            }
        }
    }
}

@Composable
fun AddQuoteDialog(
    onDismiss: () -> Unit,
    onSave: (Quote) -> Unit
) {
    var customerName by remember { mutableStateOf("") }
    var phone by remember { mutableStateOf("") }
    var division by remember { mutableStateOf(Division.FURNITURE) }
    var itemDesc by remember { mutableStateOf("") }
    var itemQty by remember { mutableStateOf("1") }
    var itemRate by remember { mutableStateOf("") }
    var itemDiscount by remember { mutableStateOf("0") }
    var gstPct by remember { mutableStateOf("18") }
    var remarks by remember { mutableStateOf("") }

    val lineItems = remember { mutableStateListOf<QuoteLineItem>() }

    Dialog(onDismissRequest = onDismiss) {
        Card(
            shape = RoundedCornerShape(20.dp),
            colors = CardDefaults.cardColors(containerColor = Color.White),
            modifier = Modifier
                .fillMaxWidth()
                .padding(vertical = 16.dp)
        ) {
            Column(
                modifier = Modifier
                    .padding(20.dp)
                    .verticalScroll(rememberScrollState())
            ) {
                Text(
                    text = "Create Proposal / Quote",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = AuraBlue
                )
                Text(
                    text = "Generate commercial quote with automated GST & discounts",
                    style = MaterialTheme.typography.bodySmall,
                    color = Slate600
                )

                Spacer(modifier = Modifier.height(14.dp))

                OutlinedTextField(
                    value = customerName,
                    onValueChange = { customerName = it },
                    label = { Text("Customer / Client Name *") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )

                Spacer(modifier = Modifier.height(8.dp))

                OutlinedTextField(
                    value = phone,
                    onValueChange = { phone = it },
                    label = { Text("Phone *") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )

                Spacer(modifier = Modifier.height(10.dp))
                Text("Division", style = MaterialTheme.typography.labelMedium)
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    listOf(Division.FURNITURE, Division.MAP, Division.DW).forEach { div ->
                        FilterChip(
                            selected = division == div,
                            onClick = { division = div },
                            label = { Text(div.shortCode) }
                        )
                    }
                }

                Spacer(modifier = Modifier.height(14.dp))
                HorizontalDivider()
                Spacer(modifier = Modifier.height(10.dp))

                Text("Add Item Line", style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.Bold)

                OutlinedTextField(
                    value = itemDesc,
                    onValueChange = { itemDesc = it },
                    label = { Text("Item Description (e.g. Dining Table 8024)") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )

                Spacer(modifier = Modifier.height(8.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    OutlinedTextField(
                        value = itemQty,
                        onValueChange = { itemQty = it },
                        label = { Text("Qty") },
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        modifier = Modifier.weight(1f),
                        singleLine = true
                    )
                    OutlinedTextField(
                        value = itemRate,
                        onValueChange = { itemRate = it },
                        label = { Text("Rate (₹)") },
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        modifier = Modifier.weight(1.5f),
                        singleLine = true
                    )
                    OutlinedTextField(
                        value = itemDiscount,
                        onValueChange = { itemDiscount = it },
                        label = { Text("Disc %") },
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        modifier = Modifier.weight(1f),
                        singleLine = true
                    )
                }

                Spacer(modifier = Modifier.height(8.dp))

                Button(
                    onClick = {
                        val rate = itemRate.toDoubleOrNull() ?: 0.0
                        val qty = itemQty.toDoubleOrNull() ?: 1.0
                        val disc = itemDiscount.toDoubleOrNull() ?: 0.0
                        if (itemDesc.isNotBlank() && rate > 0) {
                            lineItems.add(
                                QuoteLineItem(
                                    id = UUID.randomUUID().toString(),
                                    description = itemDesc.trim(),
                                    qty = qty,
                                    rate = rate,
                                    discountPct = disc,
                                    taxPct = gstPct.toDoubleOrNull() ?: 18.0
                                )
                            )
                            itemDesc = ""
                            itemRate = ""
                            itemQty = "1"
                            itemDiscount = "0"
                        }
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = Slate700),
                    modifier = Modifier.align(Alignment.End)
                ) {
                    Icon(Icons.Default.Add, contentDescription = null, modifier = Modifier.size(16.dp))
                    Spacer(modifier = Modifier.width(4.dp))
                    Text("Add Line")
                }

                if (lineItems.isNotEmpty()) {
                    Spacer(modifier = Modifier.height(10.dp))
                    Text("Current Line Items (${lineItems.size})", style = MaterialTheme.typography.labelMedium)
                    lineItems.forEachIndexed { index, item ->
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(vertical = 4.dp),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Column(modifier = Modifier.weight(1f)) {
                                Text(item.description, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold)
                                Text("${item.qty.toInt()} x ${formatInr(item.rate)}  |  Total: ${formatInr(item.total)}", style = MaterialTheme.typography.bodySmall, color = Slate600)
                            }
                            IconButton(onClick = { lineItems.removeAt(index) }) {
                                Icon(Icons.Default.Delete, contentDescription = "Delete", tint = Color.Red, modifier = Modifier.size(18.dp))
                            }
                        }
                    }
                    val totalCalc = lineItems.sumOf { it.total }
                    Text(
                        text = "Estimated Quote Total: ${formatInr(totalCalc)}",
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.Bold,
                        color = AuraBlue,
                        modifier = Modifier.padding(top = 8.dp)
                    )
                }

                Spacer(modifier = Modifier.height(16.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.End
                ) {
                    TextButton(onClick = onDismiss) {
                        Text("Cancel", color = Slate600)
                    }
                    Spacer(modifier = Modifier.width(8.dp))
                    Button(
                        onClick = {
                            if (customerName.isNotBlank() && lineItems.isNotEmpty()) {
                                onSave(
                                    Quote(
                                        id = "QT-" + System.currentTimeMillis().toString().takeLast(4),
                                        quoteNo = "MAD-QT-" + (1000..9999).random(),
                                        date = "2026-09-20",
                                        customerName = customerName.trim(),
                                        phone = phone.trim(),
                                        division = division,
                                        stage = DealStage.DESIGN_QUOTE,
                                        lineItems = lineItems.toList(),
                                        remarks = remarks
                                    )
                                )
                            }
                        },
                        colors = ButtonDefaults.buttonColors(containerColor = AuraBlue),
                        enabled = customerName.isNotBlank() && lineItems.isNotEmpty(),
                        modifier = Modifier.testTag("save_quote_button")
                    ) {
                        Text("Create Proposal")
                    }
                }
            }
        }
    }
}

@Composable
fun AddPettyCashDialog(
    onDismiss: () -> Unit,
    onSave: (PettyCashEntry) -> Unit
) {
    var type by remember { mutableStateOf("OUT") }
    var category by remember { mutableStateOf("Hardware") }
    var amount by remember { mutableStateOf("") }
    var description by remember { mutableStateOf("") }
    var party by remember { mutableStateOf("") }

    val categories = listOf("Hardware", "Fuel", "Refreshments", "Transport", "Site Advance", "Labour")

    Dialog(onDismissRequest = onDismiss) {
        Card(
            shape = RoundedCornerShape(20.dp),
            colors = CardDefaults.cardColors(containerColor = Color.White),
            modifier = Modifier.fillMaxWidth()
        ) {
            Column(
                modifier = Modifier
                    .padding(20.dp)
                    .verticalScroll(rememberScrollState())
            ) {
                Text(
                    text = "Log Cash Voucher",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = AuraBlue
                )
                Text(
                    text = "Petty cash voucher for site expenses and showroom upkeep",
                    style = MaterialTheme.typography.bodySmall,
                    color = Slate600
                )

                Spacer(modifier = Modifier.height(14.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    FilterChip(
                        selected = type == "OUT",
                        onClick = { type = "OUT" },
                        label = { Text("Expense (Cash OUT)") },
                        modifier = Modifier.weight(1f)
                    )
                    FilterChip(
                        selected = type == "IN",
                        onClick = { type = "IN" },
                        label = { Text("Top-up (Cash IN)") },
                        modifier = Modifier.weight(1f)
                    )
                }

                Spacer(modifier = Modifier.height(10.dp))

                OutlinedTextField(
                    value = amount,
                    onValueChange = { amount = it },
                    label = { Text("Amount (₹) *") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )

                Spacer(modifier = Modifier.height(10.dp))

                OutlinedTextField(
                    value = category,
                    onValueChange = { category = it },
                    label = { Text("Category (Hardware, Fuel, Refreshments, etc.)") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )

                Spacer(modifier = Modifier.height(10.dp))

                OutlinedTextField(
                    value = party,
                    onValueChange = { party = it },
                    label = { Text("Paid To / Vendor / Receiver *") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )

                Spacer(modifier = Modifier.height(10.dp))

                OutlinedTextField(
                    value = description,
                    onValueChange = { description = it },
                    label = { Text("Purpose / Description") },
                    modifier = Modifier.fillMaxWidth(),
                    maxLines = 2
                )

                Spacer(modifier = Modifier.height(16.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.End
                ) {
                    TextButton(onClick = onDismiss) { Text("Cancel") }
                    Spacer(modifier = Modifier.width(8.dp))
                    Button(
                        onClick = {
                            val amt = amount.toDoubleOrNull() ?: 0.0
                            if (amt > 0 && party.isNotBlank()) {
                                onSave(
                                    PettyCashEntry(
                                        id = "PC-" + System.currentTimeMillis().toString().takeLast(4),
                                        date = "2026-09-20",
                                        type = type,
                                        category = category.ifBlank { "General" },
                                        amount = amt,
                                        description = description,
                                        party = party.trim(),
                                        approved = true
                                    )
                                )
                            }
                        },
                        colors = ButtonDefaults.buttonColors(containerColor = AuraBlue)
                    ) {
                        Text("Record Voucher")
                    }
                }
            }
        }
    }
}

@Composable
fun AddTaskDialog(
    onDismiss: () -> Unit,
    onSave: (TaskItem) -> Unit
) {
    var title by remember { mutableStateOf("") }
    var priority by remember { mutableStateOf(TaskPriority.MEDIUM) }
    var dueDate by remember { mutableStateOf("2026-09-22") }
    var relatedTo by remember { mutableStateOf("") }

    Dialog(onDismissRequest = onDismiss) {
        Card(
            shape = RoundedCornerShape(20.dp),
            colors = CardDefaults.cardColors(containerColor = Color.White),
            modifier = Modifier.fillMaxWidth()
        ) {
            Column(
                modifier = Modifier.padding(20.dp)
            ) {
                Text(
                    text = "New Follow-up Task",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = AuraBlue
                )
                Spacer(modifier = Modifier.height(12.dp))

                OutlinedTextField(
                    value = title,
                    onValueChange = { title = it },
                    label = { Text("Task Description *") },
                    modifier = Modifier.fillMaxWidth(),
                    maxLines = 2
                )

                Spacer(modifier = Modifier.height(10.dp))

                OutlinedTextField(
                    value = relatedTo,
                    onValueChange = { relatedTo = it },
                    label = { Text("Customer / Site / Contact") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )

                Spacer(modifier = Modifier.height(10.dp))

                OutlinedTextField(
                    value = dueDate,
                    onValueChange = { dueDate = it },
                    label = { Text("Due Date (YYYY-MM-DD)") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )

                Spacer(modifier = Modifier.height(12.dp))
                Text("Priority", style = MaterialTheme.typography.labelMedium)
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    TaskPriority.values().forEach { prio ->
                        FilterChip(
                            selected = priority == prio,
                            onClick = { priority = prio },
                            label = { Text(prio.name) }
                        )
                    }
                }

                Spacer(modifier = Modifier.height(16.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.End
                ) {
                    TextButton(onClick = onDismiss) { Text("Cancel") }
                    Spacer(modifier = Modifier.width(8.dp))
                    Button(
                        onClick = {
                            if (title.isNotBlank()) {
                                onSave(
                                    TaskItem(
                                        id = "TK-" + System.currentTimeMillis().toString().takeLast(4),
                                        title = title.trim(),
                                        priority = priority,
                                        dueDate = dueDate,
                                        relatedTo = relatedTo.trim(),
                                        isDone = false
                                    )
                                )
                            }
                        },
                        colors = ButtonDefaults.buttonColors(containerColor = AuraBlue)
                    ) {
                        Text("Add Task")
                    }
                }
            }
        }
    }
}

@Composable
fun AddVisitorDialog(
    onDismiss: () -> Unit,
    onSave: (Visitor) -> Unit
) {
    var name by remember { mutableStateOf("") }
    var phone by remember { mutableStateOf("") }
    var email by remember { mutableStateOf("") }
    var division by remember { mutableStateOf(Division.FURNITURE) }
    var purpose by remember { mutableStateOf("Showroom Walk-in") }
    var interestedIn by remember { mutableStateOf("") }
    var attendedBy by remember { mutableStateOf("Sirisha Reception") }
    var notes by remember { mutableStateOf("") }

    val purposeOptions = listOf("Showroom Walk-in", "Material Selection", "Architect Meeting", "Catalog Inquiry", "Sample Testing")

    Dialog(onDismissRequest = onDismiss) {
        Card(
            shape = RoundedCornerShape(20.dp),
            colors = CardDefaults.cardColors(containerColor = Color.White),
            modifier = Modifier
                .fillMaxWidth()
                .padding(vertical = 16.dp)
        ) {
            Column(
                modifier = Modifier
                    .padding(20.dp)
                    .verticalScroll(rememberScrollState())
            ) {
                Text(
                    text = "Log Showroom Visitor",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = AuraBlue
                )
                Text(
                    text = "Reception desk entry for incoming inquiries",
                    style = MaterialTheme.typography.bodySmall,
                    color = Slate600
                )

                Spacer(modifier = Modifier.height(14.dp))

                OutlinedTextField(
                    value = name,
                    onValueChange = { name = it },
                    label = { Text("Visitor Name *") },
                    modifier = Modifier.fillMaxWidth().testTag("input_visitor_name"),
                    singleLine = true
                )

                Spacer(modifier = Modifier.height(10.dp))

                OutlinedTextField(
                    value = phone,
                    onValueChange = { phone = it },
                    label = { Text("Mobile Number *") },
                    modifier = Modifier.fillMaxWidth().testTag("input_visitor_phone"),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
                    singleLine = true
                )

                Spacer(modifier = Modifier.height(10.dp))

                OutlinedTextField(
                    value = email,
                    onValueChange = { email = it },
                    label = { Text("Email (Optional)") },
                    modifier = Modifier.fillMaxWidth(),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
                    singleLine = true
                )

                Spacer(modifier = Modifier.height(12.dp))

                Text("Division / Brand", style = MaterialTheme.typography.labelMedium)
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    listOf(Division.FURNITURE, Division.MAP, Division.DW).forEach { div ->
                        FilterChip(
                            selected = division == div,
                            onClick = { division = div },
                            label = { Text(div.displayName, fontSize = 11.sp) }
                        )
                    }
                }

                Spacer(modifier = Modifier.height(10.dp))

                OutlinedTextField(
                    value = interestedIn,
                    onValueChange = { interestedIn = it },
                    label = { Text("Interested In / Product Requirement *") },
                    placeholder = { Text("e.g. 8-seater dining, Travertino plaster, UPVC") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )

                Spacer(modifier = Modifier.height(10.dp))

                OutlinedTextField(
                    value = attendedBy,
                    onValueChange = { attendedBy = it },
                    label = { Text("Attended By (Staff / Host)") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )

                Spacer(modifier = Modifier.height(10.dp))

                OutlinedTextField(
                    value = notes,
                    onValueChange = { notes = it },
                    label = { Text("Notes / Client Context") },
                    modifier = Modifier.fillMaxWidth(),
                    maxLines = 3
                )

                Spacer(modifier = Modifier.height(16.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.End
                ) {
                    TextButton(onClick = onDismiss) { Text("Cancel") }
                    Spacer(modifier = Modifier.width(8.dp))
                    Button(
                        onClick = {
                            if (name.isNotBlank() && phone.isNotBlank()) {
                                onSave(
                                    Visitor(
                                        id = "VIS-" + System.currentTimeMillis().toString().takeLast(4),
                                        visitorNo = "VST-" + System.currentTimeMillis().toString().takeLast(4),
                                        name = name.trim(),
                                        phone = phone.trim(),
                                        email = email.trim(),
                                        purpose = purpose,
                                        division = division,
                                        interestedIn = interestedIn.trim().ifBlank { "General Inquiry" },
                                        attendedBy = attendedBy.trim(),
                                        checkInTime = "Today, Just now",
                                        status = "Inquiry Logged",
                                        notes = notes.trim()
                                    )
                                )
                            }
                        },
                        colors = ButtonDefaults.buttonColors(containerColor = AuraBlue),
                        modifier = Modifier.testTag("save_visitor_button")
                    ) {
                        Text("Log Visitor")
                    }
                }
            }
        }
    }
}

@Composable
fun ScheduleSurveyDialog(
    lead: Lead?,
    onDismiss: () -> Unit,
    onSave: (SiteSurvey) -> Unit
) {
    var clientName by remember { mutableStateOf(lead?.name ?: "") }
    var phone by remember { mutableStateOf(lead?.phone ?: "") }
    var division by remember { mutableStateOf(lead?.division ?: Division.FURNITURE) }
    var siteAddress by remember { mutableStateOf("") }
    var engineerName by remember { mutableStateOf(
        when (division) {
            Division.MAP -> "Kalyan Site PM"
            Division.DW -> "Phani Kumar"
            else -> "Veerendra"
        }
    ) }
    var surveyDate by remember { mutableStateOf("2026-09-22") }
    var measurements by remember { mutableStateOf("") }
    var wallAreaSqft by remember { mutableStateOf(if (division == Division.MAP) "3500" else "0") }
    var apertureCount by remember { mutableStateOf(if (division == Division.DW) "6" else "0") }
    var notes by remember { mutableStateOf("") }

    Dialog(onDismissRequest = onDismiss) {
        Card(
            shape = RoundedCornerShape(20.dp),
            colors = CardDefaults.cardColors(containerColor = Color.White),
            modifier = Modifier
                .fillMaxWidth()
                .padding(vertical = 16.dp)
        ) {
            Column(
                modifier = Modifier
                    .padding(20.dp)
                    .verticalScroll(rememberScrollState())
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Default.SquareFoot, contentDescription = null, tint = AuraBlue)
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(
                        text = "Site Survey & Measurement",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        color = AuraBlue
                    )
                }
                Text(
                    text = "Record site measurements to generate technical quote",
                    style = MaterialTheme.typography.bodySmall,
                    color = Slate600
                )

                Spacer(modifier = Modifier.height(14.dp))

                OutlinedTextField(
                    value = clientName,
                    onValueChange = { clientName = it },
                    label = { Text("Client Name *") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )

                Spacer(modifier = Modifier.height(10.dp))

                OutlinedTextField(
                    value = phone,
                    onValueChange = { phone = it },
                    label = { Text("Contact Phone *") },
                    modifier = Modifier.fillMaxWidth(),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
                    singleLine = true
                )

                Spacer(modifier = Modifier.height(10.dp))

                OutlinedTextField(
                    value = siteAddress,
                    onValueChange = { siteAddress = it },
                    label = { Text("Site Address / Location *") },
                    placeholder = { Text("e.g. Villa 14, Rainbow Vistas, Hitec City") },
                    modifier = Modifier.fillMaxWidth()
                )

                Spacer(modifier = Modifier.height(10.dp))

                OutlinedTextField(
                    value = engineerName,
                    onValueChange = { engineerName = it },
                    label = { Text("Assigned Site Engineer *") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )

                Spacer(modifier = Modifier.height(10.dp))

                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(
                        value = surveyDate,
                        onValueChange = { surveyDate = it },
                        label = { Text("Survey Date") },
                        modifier = Modifier.weight(1f),
                        singleLine = true
                    )
                    if (division == Division.MAP) {
                        OutlinedTextField(
                            value = wallAreaSqft,
                            onValueChange = { wallAreaSqft = it },
                            label = { Text("Wall Area (sqft)") },
                            modifier = Modifier.weight(1f),
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                            singleLine = true
                        )
                    } else if (division == Division.DW) {
                        OutlinedTextField(
                            value = apertureCount,
                            onValueChange = { apertureCount = it },
                            label = { Text("Aperture Count") },
                            modifier = Modifier.weight(1f),
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                            singleLine = true
                        )
                    }
                }

                Spacer(modifier = Modifier.height(10.dp))

                OutlinedTextField(
                    value = measurements,
                    onValueChange = { measurements = it },
                    label = { Text("Measurement Notes / Dimensions *") },
                    placeholder = { Text("e.g. Living room: 18x14ft, Window W1: 1500x1200mm, Moisture: 10%") },
                    modifier = Modifier.fillMaxWidth(),
                    maxLines = 3
                )

                Spacer(modifier = Modifier.height(10.dp))

                OutlinedTextField(
                    value = notes,
                    onValueChange = { notes = it },
                    label = { Text("Technical Remarks / Site Conditions") },
                    placeholder = { Text("Substrate moisture, scaffolding readiness, access") },
                    modifier = Modifier.fillMaxWidth(),
                    maxLines = 2
                )

                Spacer(modifier = Modifier.height(16.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.End
                ) {
                    TextButton(onClick = onDismiss) { Text("Cancel") }
                    Spacer(modifier = Modifier.width(8.dp))
                    Button(
                        onClick = {
                            if (clientName.isNotBlank() && phone.isNotBlank()) {
                                onSave(
                                    SiteSurvey(
                                        id = "SRV-" + System.currentTimeMillis().toString().takeLast(4),
                                        surveyNo = "SRV-2609-" + System.currentTimeMillis().toString().takeLast(2),
                                        leadId = lead?.id ?: "",
                                        clientName = clientName.trim(),
                                        phone = phone.trim(),
                                        siteAddress = siteAddress.trim().ifBlank { "Site Address Provided" },
                                        division = division,
                                        surveyDate = surveyDate,
                                        engineerName = engineerName.trim(),
                                        measurements = measurements.trim().ifBlank { "Standard site dimensions noted" },
                                        wallAreaSqft = wallAreaSqft.toDoubleOrNull() ?: 0.0,
                                        apertureCount = apertureCount.toIntOrNull() ?: 0,
                                        notes = notes.trim(),
                                        photoCount = 4,
                                        status = "Completed"
                                    )
                                )
                            }
                        },
                        colors = ButtonDefaults.buttonColors(containerColor = AuraBlue)
                    ) {
                        Text("Record Survey")
                    }
                }
            }
        }
    }
}

@Composable
fun AddProjectExpenseDialog(
    wallet: ProjectWallet,
    onDismiss: () -> Unit,
    onSave: (ProjectExpense) -> Unit
) {
    var amount by remember { mutableStateOf("") }
    var category by remember { mutableStateOf("Hardware/Fasteners") }
    var description by remember { mutableStateOf("") }
    var paidTo by remember { mutableStateOf("") }

    val categories = listOf(
        "Hardware/Fasteners",
        "Conveyance/Fuel",
        "Daily Labour Advance",
        "Tempo Freight/Unloading",
        "Site Refreshments",
        "Consumables"
    )

    Dialog(onDismissRequest = onDismiss) {
        Card(
            shape = RoundedCornerShape(20.dp),
            colors = CardDefaults.cardColors(containerColor = Color.White),
            modifier = Modifier
                .fillMaxWidth()
                .padding(vertical = 16.dp)
        ) {
            Column(
                modifier = Modifier
                    .padding(20.dp)
                    .verticalScroll(rememberScrollState())
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Default.AccountBalanceWallet, contentDescription = null, tint = AuraBlue)
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(
                        text = "Record Site Petty Cash Expense",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        color = AuraBlue
                    )
                }

                Surface(
                    color = Color(0xFFF1F5F9),
                    shape = RoundedCornerShape(8.dp),
                    modifier = Modifier.fillMaxWidth().padding(vertical = 10.dp)
                ) {
                    Row(
                        modifier = Modifier.padding(10.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column {
                            Text(wallet.projectName, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyMedium)
                            Text(wallet.projectNo, style = MaterialTheme.typography.bodySmall, color = Slate500)
                        }
                        Column(horizontalAlignment = Alignment.End) {
                            Text("Wallet Balance", style = MaterialTheme.typography.labelSmall, color = Slate500)
                            Text(formatInr(wallet.balance), fontWeight = FontWeight.Bold, color = SuccessGreen, style = MaterialTheme.typography.titleSmall)
                        }
                    }
                }

                OutlinedTextField(
                    value = amount,
                    onValueChange = { amount = it },
                    label = { Text("Expense Amount (₹) *") },
                    modifier = Modifier.fillMaxWidth().testTag("input_project_expense_amount"),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    singleLine = true
                )

                Spacer(modifier = Modifier.height(10.dp))

                Text("Expense Category *", style = MaterialTheme.typography.labelMedium)
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    categories.chunked(2).forEach { rowCats ->
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            rowCats.forEach { cat ->
                                FilterChip(
                                    selected = category == cat,
                                    onClick = { category = cat },
                                    label = { Text(cat, fontSize = 11.sp) }
                                )
                            }
                        }
                    }
                }

                Spacer(modifier = Modifier.height(10.dp))

                OutlinedTextField(
                    value = description,
                    onValueChange = { description = it },
                    label = { Text("Description & Purpose *") },
                    placeholder = { Text("e.g. Scaffolding anchor bolts, tempo diesel, water") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )

                Spacer(modifier = Modifier.height(10.dp))

                OutlinedTextField(
                    value = paidTo,
                    onValueChange = { paidTo = it },
                    label = { Text("Paid To (Vendor / Staff) *") },
                    placeholder = { Text("e.g. Sri Balaji Hardware, Auto driver, Mestri") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )

                Spacer(modifier = Modifier.height(16.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.End
                ) {
                    TextButton(onClick = onDismiss) { Text("Cancel") }
                    Spacer(modifier = Modifier.width(8.dp))
                    Button(
                        onClick = {
                            val amt = amount.toDoubleOrNull() ?: 0.0
                            if (amt > 0 && description.isNotBlank()) {
                                onSave(
                                    ProjectExpense(
                                        id = "PCE-" + System.currentTimeMillis().toString().takeLast(4),
                                        walletId = wallet.id,
                                        projectId = wallet.projectId,
                                        projectNo = wallet.projectNo,
                                        date = "2026-09-20",
                                        amount = amt,
                                        category = category,
                                        description = description.trim(),
                                        paidTo = paidTo.trim().ifBlank { "Site Vendor" },
                                        approved = true
                                    )
                                )
                            }
                        },
                        colors = ButtonDefaults.buttonColors(containerColor = AuraBlue)
                    ) {
                        Text("Deduct & Record")
                    }
                }
            }
        }
    }
}

@Composable
fun TopupProjectWalletDialog(
    wallet: ProjectWallet,
    onDismiss: () -> Unit,
    onSave: (Double) -> Unit
) {
    var amount by remember { mutableStateOf("15000") }

    Dialog(onDismissRequest = onDismiss) {
        Card(
            shape = RoundedCornerShape(20.dp),
            colors = CardDefaults.cardColors(containerColor = Color.White),
            modifier = Modifier.fillMaxWidth().padding(16.dp)
        ) {
            Column(modifier = Modifier.padding(20.dp)) {
                Text(
                    text = "Top-up Project Wallet",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = AuraBlue
                )
                Text(
                    text = "Allocate site funds for ${wallet.projectName} (${wallet.projectNo})",
                    style = MaterialTheme.typography.bodySmall,
                    color = Slate600
                )

                Spacer(modifier = Modifier.height(14.dp))

                OutlinedTextField(
                    value = amount,
                    onValueChange = { amount = it },
                    label = { Text("Allocation Amount (₹)") },
                    modifier = Modifier.fillMaxWidth(),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    singleLine = true
                )

                Spacer(modifier = Modifier.height(16.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.End
                ) {
                    TextButton(onClick = onDismiss) { Text("Cancel") }
                    Spacer(modifier = Modifier.width(8.dp))
                    Button(
                        onClick = {
                            val amt = amount.toDoubleOrNull() ?: 0.0
                            if (amt > 0) onSave(amt)
                        },
                        colors = ButtonDefaults.buttonColors(containerColor = AuraBlue)
                    ) {
                        Text("Allocate Funds")
                    }
                }
            }
        }
    }
}

@Composable
fun LeadJourneyDialog(
    lead: Lead,
    repository: CrmRepository,
    onDismiss: () -> Unit,
    onScheduleSurvey: () -> Unit,
    onCreateQuote: () -> Unit,
    onViewProjects: () -> Unit
) {
    val surveys by repository.surveys.collectAsState()
    val quotes by repository.quotes.collectAsState()
    val sales by repository.sales.collectAsState()
    val projects by repository.projects.collectAsState()
    val wallets by repository.projectWallets.collectAsState()
    val invoices by repository.invoices.collectAsState()

    val matchedSurvey = surveys.find { it.leadId == lead.id || it.clientName.contains(lead.name, ignoreCase = true) }
    val matchedQuote = quotes.find { it.customerName.contains(lead.name, ignoreCase = true) }
    val matchedSale = sales.find { it.customerName.contains(lead.name, ignoreCase = true) }
    val matchedProject = projects.find { it.customerName.contains(lead.name, ignoreCase = true) }
    val matchedWallet = wallets.find { it.clientName.contains(lead.name, ignoreCase = true) || (matchedProject != null && it.projectId == matchedProject.id) }
    val matchedInvoice = invoices.find { it.customerName.contains(lead.name, ignoreCase = true) }

    Dialog(onDismissRequest = onDismiss) {
        Card(
            shape = RoundedCornerShape(20.dp),
            colors = CardDefaults.cardColors(containerColor = Color.White),
            modifier = Modifier
                .fillMaxWidth()
                .padding(vertical = 16.dp)
        ) {
            Column(
                modifier = Modifier
                    .padding(20.dp)
                    .verticalScroll(rememberScrollState())
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column {
                        Text(
                            text = "Linked Lifecycle Flow",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold,
                            color = AuraBlue
                        )
                        Text(
                            text = "${lead.name} (${lead.division.displayName})",
                            style = MaterialTheme.typography.bodySmall,
                            color = Slate600
                        )
                    }
                    IconButton(onClick = onDismiss) {
                        Icon(Icons.Default.Close, contentDescription = "Close", tint = Slate500)
                    }
                }

                Spacer(modifier = Modifier.height(14.dp))

                // Stepper Items
                LifecycleStepItem(
                    stepNumber = "1",
                    title = "Visitor Inquiry",
                    status = if (lead.source.contains("Visitor", ignoreCase = true) || lead.visitorId != null) "Logged at Showroom" else "Direct Lead (${lead.source})",
                    isComplete = true,
                    details = "Source: ${lead.source}. Created: ${lead.createdAt.ifBlank { "Recently" }}"
                )

                LifecycleStepItem(
                    stepNumber = "2",
                    title = "Sales Lead",
                    status = lead.stage.displayName,
                    isComplete = true,
                    details = "Est. Value: ${formatInr(lead.estimatedValue)} | Confidence: ${lead.confidenceLevel}%"
                )

                LifecycleStepItem(
                    stepNumber = "3",
                    title = "Site Survey",
                    status = if (matchedSurvey != null) "Survey Done (${matchedSurvey.surveyNo})" else "Not Conducted",
                    isComplete = matchedSurvey != null,
                    details = if (matchedSurvey != null)
                        "Specs: ${matchedSurvey.measurements.take(45)}... Engineer: ${matchedSurvey.engineerName}"
                    else "Laser measurements & site aperture inspection required.",
                    actionButton = if (matchedSurvey == null) {
                        {
                            TextButton(onClick = onScheduleSurvey) {
                                Text("Schedule Survey", fontSize = 12.sp, color = AuraBlue)
                            }
                        }
                    } else null
                )

                LifecycleStepItem(
                    stepNumber = "4",
                    title = "Quotation Proposal",
                    status = if (matchedQuote != null) "Quote Generated (${matchedQuote.quoteNo})" else "Pending Quote",
                    isComplete = matchedQuote != null,
                    details = if (matchedQuote != null)
                        "Grand Total: ${formatInr(matchedQuote.grandTotal)} (${matchedQuote.lineItems.size} items)"
                    else "Proposal pending client requirement finalization.",
                    actionButton = if (matchedQuote == null) {
                        {
                            TextButton(onClick = onCreateQuote) {
                                Text("Generate Quote", fontSize = 12.sp, color = AuraBlue)
                            }
                        }
                    } else null
                )

                LifecycleStepItem(
                    stepNumber = "5",
                    title = "Confirmed Sale",
                    status = if (matchedSale != null) "Order Booked (${matchedSale.saleNo})" else "Awaiting Closure",
                    isComplete = matchedSale != null,
                    details = if (matchedSale != null)
                        "Value: ${formatInr(matchedSale.totalValue)} | Paid: ${formatInr(matchedSale.paidAmount)}"
                    else "Converted once quotation is approved by client."
                )

                LifecycleStepItem(
                    stepNumber = "6",
                    title = "Project Execution",
                    status = if (matchedProject != null) "Under Execution (${matchedProject.stage})" else "Not Initiated",
                    isComplete = matchedProject != null,
                    details = if (matchedProject != null)
                        "Site: ${matchedProject.siteAddress} (${matchedProject.completionPct}% complete)"
                    else "Triggered automatically upon sale order booking.",
                    actionButton = if (matchedProject != null) {
                        {
                            TextButton(onClick = onViewProjects) {
                                Text("View Project", fontSize = 12.sp, color = AuraBlue)
                            }
                        }
                    } else null
                )

                LifecycleStepItem(
                    stepNumber = "7",
                    title = "Project Petty Cash Wallet",
                    status = if (matchedWallet != null) "Wallet Active (${matchedWallet.projectNo})" else "Not Allocated",
                    isComplete = matchedWallet != null,
                    details = if (matchedWallet != null)
                        "Allocated: ${formatInr(matchedWallet.totalAllocated)} | Balance: ${formatInr(matchedWallet.balance)}"
                    else "Project wallet allocates site engineer petty cash."
                )

                LifecycleStepItem(
                    stepNumber = "8",
                    title = "Finance & Tax Invoice",
                    status = if (matchedInvoice != null) "Invoice Issued (${matchedInvoice.invoiceNo})" else "Pending",
                    isComplete = matchedInvoice != null,
                    details = if (matchedInvoice != null)
                        "Total: ${formatInr(matchedInvoice.totalAmount)} | Status: ${matchedInvoice.status}"
                    else "Tax invoice for advance/completion settlement."
                )

                Spacer(modifier = Modifier.height(16.dp))

                Button(
                    onClick = onDismiss,
                    colors = ButtonDefaults.buttonColors(containerColor = Slate800),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text("Done")
                }
            }
        }
    }
}

@Composable
fun LifecycleStepItem(
    stepNumber: String,
    title: String,
    status: String,
    isComplete: Boolean,
    details: String,
    actionButton: (@Composable () -> Unit)? = null
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 6.dp),
        verticalAlignment = Alignment.Top
    ) {
        Box(
            modifier = Modifier
                .size(28.dp)
                .clip(CircleShape)
                .background(if (isComplete) SuccessGreen else Slate200),
            contentAlignment = Alignment.Center
        ) {
            if (isComplete) {
                Icon(Icons.Default.Check, contentDescription = null, tint = Color.White, modifier = Modifier.size(16.dp))
            } else {
                Text(stepNumber, fontWeight = FontWeight.Bold, fontSize = 12.sp, color = Slate600)
            }
        }

        Spacer(modifier = Modifier.width(12.dp))

        Column(modifier = Modifier.weight(1f)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(title, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyMedium, color = Slate900)
                Surface(
                    color = if (isComplete) SuccessGreenLight else Slate100,
                    shape = RoundedCornerShape(4.dp)
                ) {
                    Text(
                        text = status,
                        fontSize = 10.sp,
                        fontWeight = FontWeight.SemiBold,
                        color = if (isComplete) SuccessGreen else Slate600,
                        modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                    )
                }
            }
            Text(details, style = MaterialTheme.typography.bodySmall, color = Slate500, fontSize = 11.sp)
            if (actionButton != null) {
                actionButton()
            }
        }
    }
}

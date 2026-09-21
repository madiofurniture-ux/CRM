package com.example.madiocrm.ui.screens

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
import androidx.compose.ui.window.Dialog
import com.example.madiocrm.data.model.*
import com.example.madiocrm.data.repository.CrmRepository
import com.example.madiocrm.ui.components.*
import com.example.madiocrm.ui.theme.*

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PipelineScreen(
    repository: CrmRepository,
    onOpenAddQuote: () -> Unit,
    modifier: Modifier = Modifier
) {
    val quotes by repository.quotes.collectAsState()
    val surveys by repository.surveys.collectAsState()

    var activeTab by remember { mutableIntStateOf(0) } // 0: Quotes, 1: Site Surveys
    var selectedDivision by remember { mutableStateOf(Division.ALL) }
    var selectedQuoteForDetail by remember { mutableStateOf<Quote?>(null) }
    var actionNotification by remember { mutableStateOf<String?>(null) }

    val filteredQuotes = remember(quotes, selectedDivision) {
        if (selectedDivision == Division.ALL) quotes else quotes.filter { it.division == selectedDivision }
    }

    val filteredSurveys = remember(surveys, selectedDivision) {
        if (selectedDivision == Division.ALL) surveys else surveys.filter { it.division == selectedDivision }
    }

    val totalPipelineValue = filteredQuotes.sumOf { it.grandTotal }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text(if (activeTab == 0) "Quotes & Deals Pipeline" else "Site Surveys & Laser Measurements", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleLarge)
                        Text(
                            if (activeTab == 0) "Total Pipeline: ${formatInr(totalPipelineValue)}" else "${filteredSurveys.size} site surveys recorded",
                            style = MaterialTheme.typography.bodySmall,
                            color = Slate500
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = Color.White),
                actions = {
                    if (activeTab == 0) {
                        IconButton(
                            onClick = onOpenAddQuote,
                            modifier = Modifier.testTag("add_quote_top_button")
                        ) {
                            Icon(Icons.Default.PostAdd, contentDescription = "New Quote", tint = AuraBlue)
                        }
                    }
                }
            )
        },
        floatingActionButton = {
            if (activeTab == 0) {
                FloatingActionButton(
                    onClick = onOpenAddQuote,
                    containerColor = AuraBlue,
                    contentColor = Color.White,
                    shape = CircleShape,
                    modifier = Modifier
                        .padding(bottom = 60.dp)
                        .testTag("quotes_fab_add")
                ) {
                    Icon(Icons.Default.Add, contentDescription = "New Quote")
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
                selectedTabIndex = activeTab,
                containerColor = Color.White,
                contentColor = AuraBlue
            ) {
                Tab(
                    selected = activeTab == 0,
                    onClick = { activeTab = 0 },
                    text = {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Default.RequestQuote, contentDescription = null, modifier = Modifier.size(16.dp))
                            Spacer(modifier = Modifier.width(4.dp))
                            Text("Quotations (${quotes.size})", fontWeight = if (activeTab == 0) FontWeight.Bold else FontWeight.Normal)
                        }
                    }
                )
                Tab(
                    selected = activeTab == 1,
                    onClick = { activeTab = 1 },
                    text = {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Default.SquareFoot, contentDescription = null, modifier = Modifier.size(16.dp))
                            Spacer(modifier = Modifier.width(4.dp))
                            Text("Site Surveys (${surveys.size})", fontWeight = if (activeTab == 1) FontWeight.Bold else FontWeight.Normal)
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
                    items(filteredQuotes, key = { it.id }) { quote ->
                        QuoteCard(
                            quote = quote,
                            onStageChange = { newStage ->
                                repository.updateQuoteStage(quote.id, newStage)
                            },
                            onConvertToSale = {
                                val sale = repository.convertQuoteToSale(quote)
                                actionNotification = "Won & Booked! Created Sale Order ${sale.saleNo}, initiated project execution, and allocated petty cash wallet."
                            },
                            onClick = { selectedQuoteForDetail = quote }
                        )
                    }
                }
            } else {
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 8.dp, bottom = 80.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    items(filteredSurveys, key = { it.id }) { survey ->
                        SurveyCard(
                            survey = survey,
                            onConvertToQuote = {
                                val quote = repository.convertSurveyToQuote(survey)
                                actionNotification = "Created Quotation ${quote.quoteNo} from Site Survey (${survey.clientName})!"
                            }
                        )
                    }
                }
            }
        }
    }

    // Quote Detail & Line Items Dialog
    selectedQuoteForDetail?.let { quote ->
        QuoteDetailDialog(
            quote = quote,
            onDismiss = { selectedQuoteForDetail = null },
            onConvertToSale = {
                val sale = repository.convertQuoteToSale(quote)
                selectedQuoteForDetail = null
                actionNotification = "Won & Booked! Created Sale Order ${sale.saleNo}, initiated project execution, and allocated petty cash wallet."
            }
        )
    }

    actionNotification?.let { msg ->
        AlertDialog(
            onDismissRequest = { actionNotification = null },
            title = { Text("Pipeline Flow Update", fontWeight = FontWeight.Bold, color = AuraBlue) },
            text = { Text(msg) },
            confirmButton = {
                Button(
                    onClick = { actionNotification = null },
                    colors = ButtonDefaults.buttonColors(containerColor = AuraBlue)
                ) {
                    Text("OK")
                }
            }
        )
    }
}

@Composable
fun QuoteCard(
    quote: Quote,
    onStageChange: (DealStage) -> Unit,
    onConvertToSale: () -> Unit,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    var showStageMenu by remember { mutableStateOf(false) }

    Card(
        colors = CardDefaults.cardColors(containerColor = Color.White),
        shape = RoundedCornerShape(16.dp),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
        modifier = modifier
            .fillMaxWidth()
            .clickable { onClick() }
            .testTag("quote_card_${quote.id}")
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(quote.quoteNo, style = MaterialTheme.typography.labelLarge, color = AuraBlue, fontWeight = FontWeight.Bold)
                        Spacer(modifier = Modifier.width(6.dp))
                        DivisionBadge(quote.division)
                    }
                    Text(quote.customerName, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = Slate900)
                }
                Box {
                    Surface(
                        shape = RoundedCornerShape(12.dp),
                        modifier = Modifier.clickable { showStageMenu = true }
                    ) {
                        DealStageBadge(quote.stage)
                    }
                    DropdownMenu(
                        expanded = showStageMenu,
                        onDismissRequest = { showStageMenu = false }
                    ) {
                        DealStage.values().forEach { stage ->
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

            Spacer(modifier = Modifier.height(10.dp))

            // Line items brief
            Text(
                text = "${quote.lineItems.size} Line Items: " + quote.lineItems.joinToString(", ") { it.description },
                style = MaterialTheme.typography.bodySmall,
                color = Slate600,
                maxLines = 2
            )

            Spacer(modifier = Modifier.height(12.dp))
            HorizontalDivider(color = Slate100)
            Spacer(modifier = Modifier.height(8.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column {
                    Text("Total (Incl. GST)", style = MaterialTheme.typography.labelMedium, color = Slate400, fontSize = 10.sp)
                    Text(formatInr(quote.grandTotal), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = Slate900)
                }

                if (quote.stage != DealStage.WON) {
                    Button(
                        onClick = onConvertToSale,
                        colors = ButtonDefaults.buttonColors(containerColor = SuccessGreen),
                        shape = RoundedCornerShape(10.dp),
                        contentPadding = PaddingValues(horizontal = 12.dp, vertical = 6.dp),
                        modifier = Modifier.testTag("convert_sale_button_${quote.id}")
                    ) {
                        Icon(Icons.Default.CheckCircle, contentDescription = null, modifier = Modifier.size(16.dp))
                        Spacer(modifier = Modifier.width(4.dp))
                        Text("Win & Book Sale", fontSize = 12.sp)
                    }
                } else {
                    Surface(
                        color = SuccessGreenLight,
                        shape = RoundedCornerShape(8.dp)
                    ) {
                        Text(
                            "Sale Order Booked",
                            color = SuccessGreen,
                            fontWeight = FontWeight.Bold,
                            style = MaterialTheme.typography.labelMedium,
                            modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                        )
                    }
                }
            }
        }
    }
}

@Composable
fun SurveyCard(
    survey: SiteSurvey,
    onConvertToQuote: () -> Unit,
    modifier: Modifier = Modifier
) {
    val isConverted = survey.status == "Converted to Quote"

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
                        Text(survey.surveyNo, style = MaterialTheme.typography.labelLarge, color = AuraBlue, fontWeight = FontWeight.Bold)
                        Spacer(modifier = Modifier.width(6.dp))
                        DivisionBadge(survey.division)
                    }
                    Text(survey.clientName, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = Slate900)
                }

                Surface(
                    color = if (isConverted) SuccessGreenLight else Color(0xFFEFF6FF),
                    shape = RoundedCornerShape(8.dp)
                ) {
                    Text(
                        survey.status,
                        fontSize = 11.sp,
                        fontWeight = FontWeight.Bold,
                        color = if (isConverted) SuccessGreen else AuraBlue,
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 3.dp)
                    )
                }
            }

            Spacer(modifier = Modifier.height(8.dp))

            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Default.LocationOn, contentDescription = null, tint = Slate400, modifier = Modifier.size(15.dp))
                Spacer(modifier = Modifier.width(4.dp))
                Text(survey.siteAddress, style = MaterialTheme.typography.bodySmall, color = Slate600)
            }

            Spacer(modifier = Modifier.height(4.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Default.Person, contentDescription = null, tint = Slate400, modifier = Modifier.size(15.dp))
                    Spacer(modifier = Modifier.width(4.dp))
                    Text("Engineer: ${survey.engineerName}", style = MaterialTheme.typography.bodySmall, color = Slate700)
                }
                Text("Date: ${survey.surveyDate}", style = MaterialTheme.typography.bodySmall, color = Slate500)
            }

            Spacer(modifier = Modifier.height(8.dp))

            Surface(
                color = Color(0xFFF8FAFC),
                shape = RoundedCornerShape(8.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(modifier = Modifier.padding(10.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Default.Straighten, contentDescription = null, tint = AuraBlue, modifier = Modifier.size(14.dp))
                        Spacer(modifier = Modifier.width(6.dp))
                        Text(
                            "Measurements: ${survey.apertureCount} apertures / ${survey.wallAreaSqft.toInt()} sq ft",
                            fontSize = 11.sp,
                            fontWeight = FontWeight.SemiBold,
                            color = Slate800
                        )
                    }
                    Spacer(modifier = Modifier.height(3.dp))
                    Text("Details: ${survey.measurements}", fontSize = 11.sp, color = Slate600)
                    Text("Moisture / Substrate: ${survey.moistureLevel} • Photos: ${survey.photoCount} attached", fontSize = 10.sp, color = Slate500)
                }
            }

            Spacer(modifier = Modifier.height(10.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.End
            ) {
                if (!isConverted) {
                    Button(
                        onClick = onConvertToQuote,
                        colors = ButtonDefaults.buttonColors(containerColor = AuraBlue),
                        shape = RoundedCornerShape(8.dp),
                        contentPadding = PaddingValues(horizontal = 12.dp, vertical = 4.dp)
                    ) {
                        Icon(Icons.Default.RequestQuote, contentDescription = null, modifier = Modifier.size(14.dp))
                        Spacer(modifier = Modifier.width(4.dp))
                        Text("Generate Quote from Survey", fontSize = 11.sp, fontWeight = FontWeight.Bold)
                    }
                } else {
                    Text(
                        "Quote ${survey.linkedQuoteId ?: ""} Generated",
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
fun QuoteDetailDialog(
    quote: Quote,
    onDismiss: () -> Unit,
    onConvertToSale: () -> Unit
) {
    Dialog(onDismissRequest = onDismiss) {
        Card(
            shape = RoundedCornerShape(16.dp),
            colors = CardDefaults.cardColors(containerColor = Color.White),
            modifier = Modifier.fillMaxWidth()
        ) {
            Column(modifier = Modifier.padding(20.dp)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column {
                        Text(quote.quoteNo, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, color = AuraBlue)
                        Text(quote.customerName, style = MaterialTheme.typography.bodyMedium, color = Slate700)
                    }
                    DivisionBadge(quote.division)
                }

                Spacer(modifier = Modifier.height(12.dp))
                HorizontalDivider(color = Slate200)
                Spacer(modifier = Modifier.height(12.dp))

                Text("Line Items & Bill of Quantities:", fontWeight = FontWeight.Bold, fontSize = 12.sp, color = Slate800)
                Spacer(modifier = Modifier.height(6.dp))

                quote.lineItems.forEach { item ->
                    Surface(
                        color = Color(0xFFF8FAFC),
                        shape = RoundedCornerShape(6.dp),
                        modifier = Modifier.fillMaxWidth().padding(vertical = 3.dp)
                    ) {
                        Row(
                            modifier = Modifier.padding(8.dp),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Column(modifier = Modifier.weight(1f)) {
                                Text(item.description, fontSize = 11.sp, fontWeight = FontWeight.SemiBold, color = Slate900)
                                Text("${item.qty} ${item.unit} @ ${formatInr(item.rate)} (+${item.taxPct}% GST)", fontSize = 10.sp, color = Slate500)
                            }
                            Text(formatInr(item.total), fontSize = 11.sp, fontWeight = FontWeight.Bold, color = Slate800)
                        }
                    }
                }

                Spacer(modifier = Modifier.height(12.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Text("Grand Total:", fontWeight = FontWeight.Bold, color = Slate900)
                    Text(formatInr(quote.grandTotal), fontWeight = FontWeight.Bold, color = AuraBlue, fontSize = 16.sp)
                }

                Spacer(modifier = Modifier.height(16.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.End,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    TextButton(onClick = onDismiss) {
                        Text("Close", color = Slate600)
                    }
                    Spacer(modifier = Modifier.width(8.dp))
                    if (quote.stage != DealStage.WON) {
                        Button(
                            onClick = onConvertToSale,
                            colors = ButtonDefaults.buttonColors(containerColor = SuccessGreen)
                        ) {
                            Icon(Icons.Default.CheckCircle, contentDescription = null, modifier = Modifier.size(16.dp))
                            Spacer(modifier = Modifier.width(4.dp))
                            Text("Win & Book Sale")
                        }
                    }
                }
            }
        }
    }
}

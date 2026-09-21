package com.example.madiocrm

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.madiocrm.data.model.Lead
import com.example.madiocrm.data.model.Quote
import com.example.madiocrm.data.repository.CrmRepository
import com.example.madiocrm.ui.components.AddLeadDialog
import com.example.madiocrm.ui.components.AddQuoteDialog
import com.example.madiocrm.ui.screens.*
import com.example.madiocrm.ui.theme.AuraBlue
import com.example.madiocrm.ui.theme.MadioCrmTheme
import com.example.madiocrm.ui.theme.Slate400

enum class CrmNavDestination(
    val title: String,
    val icon: ImageVector,
    val testTag: String
) {
    VISITORS("Visitors", Icons.Default.Storefront, "nav_visitors"),
    LEADS("Leads", Icons.Default.People, "nav_leads"),
    QUOTES("Quotes", Icons.Default.Description, "nav_quotes"),
    PROJECTS("Projects", Icons.Default.Engineering, "nav_projects"),
    PETTY_CASH("Petty Cash", Icons.Default.AccountBalanceWallet, "nav_petty_cash"),
    CHAT("Team Chat", Icons.Default.Forum, "nav_chat"),
    DASHBOARD("Overview", Icons.Default.Dashboard, "nav_dashboard"),
    PIPELINE("Quotes", Icons.Default.Description, "nav_pipeline"),
    FINANCE("Finance", Icons.Default.AccountBalanceWallet, "nav_finance"),
    SALES("Sales", Icons.Default.PointOfSale, "nav_sales"),
    ATTENDANCE("Attendance", Icons.Default.Badge, "nav_attendance"),
    INVENTORY("Stock", Icons.Default.Inventory2, "nav_inventory"),
    TASKS("Tasks", Icons.Default.Checklist, "nav_tasks")
}

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            MadioCrmTheme {
                MainAppShell()
            }
        }
    }
}

@Composable
fun MainAppShell() {
    val repository = remember { CrmRepository.getInstance() }
    var currentDestination by remember { mutableStateOf(CrmNavDestination.VISITORS) }
    var targetChatGroupId by remember { mutableStateOf<String?>(null) }

    val chatGroups by repository.chatGroups.collectAsState()
    val totalUnreadChats = remember(chatGroups) { chatGroups.sumOf { it.unreadCount } }

    var showAddLeadDialog by remember { mutableStateOf(false) }
    var showAddQuoteDialog by remember { mutableStateOf(false) }

    Scaffold(
        bottomBar = {
            NavigationBar(
                containerColor = Color.White,
                tonalElevation = 8.dp,
                modifier = Modifier.testTag("crm_bottom_navigation")
            ) {
                listOf(
                    CrmNavDestination.VISITORS,
                    CrmNavDestination.LEADS,
                    CrmNavDestination.QUOTES,
                    CrmNavDestination.PROJECTS,
                    CrmNavDestination.PETTY_CASH
                ).forEach { item ->
                    val isSelected = currentDestination == item
                    NavigationBarItem(
                        selected = isSelected,
                        onClick = { currentDestination = item },
                        icon = {
                            Icon(
                                imageVector = item.icon,
                                contentDescription = item.title
                            )
                        },
                        label = {
                            Text(
                                text = item.title,
                                maxLines = 1,
                                fontSize = 11.sp,
                                fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Medium
                            )
                        },
                        colors = NavigationBarItemDefaults.colors(
                            selectedIconColor = AuraBlue,
                            selectedTextColor = AuraBlue,
                            unselectedIconColor = Slate400,
                            unselectedTextColor = Slate400,
                            indicatorColor = Color(0xFFE8F1FC)
                        ),
                        modifier = Modifier.testTag(item.testTag)
                    )
                }
            }
        }
    ) { paddingValues ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
        ) {
            when (currentDestination) {
                CrmNavDestination.VISITORS -> VisitorsScreen(
                    repository = repository,
                    onNavigateToLeads = { currentDestination = CrmNavDestination.LEADS }
                )
                CrmNavDestination.LEADS -> LeadsScreen(
                    repository = repository,
                    onOpenAddLead = { showAddLeadDialog = true },
                    onConvertToQuote = { lead ->
                        showAddQuoteDialog = true
                    },
                    onNavigateToProjects = {
                        currentDestination = CrmNavDestination.PROJECTS
                    }
                )
                CrmNavDestination.QUOTES, CrmNavDestination.PIPELINE -> PipelineScreen(
                    repository = repository,
                    onOpenAddQuote = { showAddQuoteDialog = true }
                )
                CrmNavDestination.PROJECTS -> ProjectsScreen(
                    repository = repository,
                    onOpenProjectChat = { project ->
                        val group = repository.getOrCreateGroupForProject(project)
                        targetChatGroupId = group.id
                        currentDestination = CrmNavDestination.CHAT
                    },
                    onOpenAllChats = {
                        targetChatGroupId = null
                        currentDestination = CrmNavDestination.CHAT
                    }
                )
                CrmNavDestination.PETTY_CASH, CrmNavDestination.FINANCE -> PettyCashScreen(
                    repository = repository,
                    onNavigateToProjects = {
                        currentDestination = CrmNavDestination.PROJECTS
                    }
                )
                CrmNavDestination.CHAT -> ChatScreen(
                    repository = repository,
                    initialGroupId = targetChatGroupId,
                    onNavigateToProject = {
                        currentDestination = CrmNavDestination.PROJECTS
                    }
                )
                CrmNavDestination.DASHBOARD -> DashboardScreen(
                    repository = repository,
                    onNavigateToLeads = { currentDestination = CrmNavDestination.LEADS },
                    onNavigateToQuotes = { currentDestination = CrmNavDestination.QUOTES },
                    onNavigateToSales = { currentDestination = CrmNavDestination.SALES },
                    onNavigateToProjects = { currentDestination = CrmNavDestination.PROJECTS },
                    onNavigateToInventory = { currentDestination = CrmNavDestination.INVENTORY },
                    onOpenAddLead = { showAddLeadDialog = true },
                    onNavigateToChat = {
                        targetChatGroupId = null
                        currentDestination = CrmNavDestination.CHAT
                    }
                )
                CrmNavDestination.SALES -> SalesScreen(
                    repository = repository
                )
                CrmNavDestination.ATTENDANCE -> AttendanceScreen(
                    repository = repository
                )
                CrmNavDestination.INVENTORY -> InventoryScreen(
                    repository = repository
                )
                CrmNavDestination.TASKS -> TasksScreen(
                    repository = repository
                )
            }
        }
    }

    if (showAddLeadDialog) {
        AddLeadDialog(
            onDismiss = { showAddLeadDialog = false },
            onSave = { lead ->
                repository.addLead(lead)
                showAddLeadDialog = false
            }
        )
    }

    if (showAddQuoteDialog) {
        AddQuoteDialog(
            onDismiss = { showAddQuoteDialog = false },
            onSave = { quote ->
                repository.addQuote(quote)
                showAddQuoteDialog = false
            }
        )
    }
}

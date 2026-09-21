package com.example.madiocrm.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Event
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.madiocrm.data.model.TaskItem
import com.example.madiocrm.data.model.TaskPriority
import com.example.madiocrm.data.repository.CrmRepository
import com.example.madiocrm.ui.components.AddTaskDialog
import com.example.madiocrm.ui.theme.*

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TasksScreen(
    repository: CrmRepository,
    modifier: Modifier = Modifier
) {
    val tasks by repository.tasks.collectAsState()
    var showOnlyPending by remember { mutableStateOf(true) }
    var showAddTaskDialog by remember { mutableStateOf(false) }

    val filteredTasks = remember(tasks, showOnlyPending) {
        if (showOnlyPending) tasks.filter { !it.isDone } else tasks
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text("Follow-ups & Tasks", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleLarge)
                        Text("${tasks.count { !it.isDone }} pending follow-ups", style = MaterialTheme.typography.bodySmall, color = Slate500)
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = Color.White)
            )
        },
        floatingActionButton = {
            FloatingActionButton(
                onClick = { showAddTaskDialog = true },
                containerColor = AuraBlue,
                contentColor = Color.White,
                shape = CircleShape,
                modifier = Modifier
                    .padding(bottom = 60.dp)
                    .testTag("tasks_fab_add")
            ) {
                Icon(Icons.Default.Add, contentDescription = "New Task")
            }
        }
    ) { innerPadding ->
        Column(
            modifier = modifier
                .fillMaxSize()
                .background(Slate50)
                .padding(innerPadding)
        ) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 8.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                FilterChip(
                    selected = showOnlyPending,
                    onClick = { showOnlyPending = true },
                    label = { Text("Pending (${tasks.count { !it.isDone }})") }
                )
                FilterChip(
                    selected = !showOnlyPending,
                    onClick = { showOnlyPending = false },
                    label = { Text("All Tasks (${tasks.size})") }
                )
            }

            LazyColumn(
                modifier = Modifier.fillMaxSize(),
                contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 4.dp, bottom = 80.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                items(filteredTasks, key = { it.id }) { task ->
                    TaskCard(
                        task = task,
                        onToggle = { repository.toggleTask(task.id) }
                    )
                }
            }
        }
    }

    if (showAddTaskDialog) {
        AddTaskDialog(
            onDismiss = { showAddTaskDialog = false },
            onSave = { task ->
                repository.addTask(task)
                showAddTaskDialog = false
            }
        )
    }
}

@Composable
fun TaskCard(
    task: TaskItem,
    onToggle: () -> Unit,
    modifier: Modifier = Modifier
) {
    Card(
        colors = CardDefaults.cardColors(containerColor = Color.White),
        shape = RoundedCornerShape(14.dp),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
        modifier = modifier
            .fillMaxWidth()
            .testTag("task_card_${task.id}")
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Checkbox(
                checked = task.isDone,
                onCheckedChange = { onToggle() },
                colors = CheckboxDefaults.colors(
                    checkedColor = SuccessGreen,
                    checkmarkColor = Color.White
                ),
                modifier = Modifier.testTag("task_checkbox_${task.id}")
            )

            Spacer(modifier = Modifier.width(6.dp))

            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = task.title,
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = if (task.isDone) FontWeight.Normal else FontWeight.SemiBold,
                    color = if (task.isDone) Slate400 else Slate900,
                    textDecoration = if (task.isDone) TextDecoration.LineThrough else TextDecoration.None
                )
                Spacer(modifier = Modifier.height(3.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    if (task.relatedTo.isNotBlank()) {
                        Text(
                            text = "${task.relatedTo}  •  ",
                            style = MaterialTheme.typography.bodySmall,
                            color = AuraBlue,
                            fontWeight = FontWeight.Medium
                        )
                    }
                    Icon(Icons.Default.Event, contentDescription = null, tint = Slate400, modifier = Modifier.size(13.dp))
                    Spacer(modifier = Modifier.width(2.dp))
                    Text(
                        text = task.dueDate,
                        style = MaterialTheme.typography.bodySmall,
                        color = Slate500,
                        fontSize = 11.sp
                    )
                }
            }

            val (prioBg, prioFg) = when (task.priority) {
                TaskPriority.URGENT -> DangerRedLight to DangerRed
                TaskPriority.HIGH -> WarningAmberLight to Color(0xFFB45309)
                TaskPriority.MEDIUM -> AuraBlueLight to AuraBlue
                TaskPriority.LOW -> Slate100 to Slate600
            }
            Surface(
                color = prioBg,
                shape = RoundedCornerShape(6.dp)
            ) {
                Text(
                    text = task.priority.name,
                    color = prioFg,
                    style = MaterialTheme.typography.labelSmall,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                )
            }
        }
    }
}

package com.example.madiocrm.ui.screens

import android.graphics.Bitmap
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.*
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import com.example.madiocrm.data.model.*
import com.example.madiocrm.data.repository.CrmRepository
import com.example.madiocrm.ui.components.DivisionBadge
import com.example.madiocrm.ui.components.formatInr
import com.example.madiocrm.ui.theme.*

// WhatsApp Theme Color Palette
val WhatsAppDarkTeal = Color(0xFF075E54)
val WhatsAppGreen = Color(0xFF25D366)
val WhatsAppOutgoingBubble = Color(0xFFE7FFDB)
val WhatsAppIncomingBubble = Color(0xFFFFFFFF)
val WhatsAppWallpaperBg = Color(0xFFECE5DD)
val WhatsAppBlueTicks = Color(0xFF34B7F1)
val WhatsAppSystemChip = Color(0xFFFFF3CD)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ChatScreen(
    repository: CrmRepository,
    initialGroupId: String? = null,
    onNavigateToProject: ((String) -> Unit)? = null,
    modifier: Modifier = Modifier
) {
    val groups by repository.chatGroups.collectAsState()
    val projects by repository.projects.collectAsState()
    val allMessages by repository.chatMessages.collectAsState()

    var selectedGroupId by remember(initialGroupId) { mutableStateOf(initialGroupId) }
    var showCreateGroupDialog by remember { mutableStateOf(false) }

    val activeGroup = groups.firstOrNull { it.id == selectedGroupId }

    if (activeGroup != null) {
        val messages = allMessages[activeGroup.id] ?: emptyList()
        val linkedProject = remember(activeGroup.projectId, projects) {
            projects.firstOrNull { it.id == activeGroup.projectId || it.projectNo == activeGroup.projectNo }
        }

        ChatConversationView(
            group = activeGroup,
            linkedProject = linkedProject,
            messages = messages,
            onBack = { selectedGroupId = null },
            onSendMessage = { text, attachment, isConfidential ->
                repository.sendChatMessage(
                    groupId = activeGroup.id,
                    text = text,
                    attachment = attachment,
                    isConfidential = isConfidential
                )
            },
            onNavigateToProject = onNavigateToProject,
            modifier = modifier
        )
    } else {
        ChatGroupsListView(
            groups = groups,
            projects = projects,
            onSelectGroup = { group ->
                repository.markGroupAsRead(group.id)
                selectedGroupId = group.id
            },
            onCreateGroupClick = { showCreateGroupDialog = true },
            modifier = modifier
        )
    }

    if (showCreateGroupDialog) {
        CreateChatGroupDialog(
            projects = projects,
            onDismiss = { showCreateGroupDialog = false },
            onCreate = { newGroup, initMsg ->
                val created = repository.createChatGroup(newGroup, initMsg)
                showCreateGroupDialog = false
                selectedGroupId = created.id
            }
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ChatGroupsListView(
    groups: List<ChatGroup>,
    projects: List<Project>,
    onSelectGroup: (ChatGroup) -> Unit,
    onCreateGroupClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    var searchQuery by remember { mutableStateOf("") }
    var selectedFilter by remember { mutableStateOf("ALL") } // ALL, LINKED, CONFIDENTIAL, FURNITURE, MAP

    val filteredGroups = remember(groups, searchQuery, selectedFilter) {
        groups.filter { group ->
            val matchesSearch = searchQuery.isBlank() ||
                    group.name.contains(searchQuery, ignoreCase = true) ||
                    (group.projectName?.contains(searchQuery, ignoreCase = true) == true) ||
                    group.lastMessage.contains(searchQuery, ignoreCase = true)

            val matchesFilter = when (selectedFilter) {
                "LINKED" -> group.projectId != null
                "CONFIDENTIAL" -> group.isConfidential
                "FURNITURE" -> group.division == Division.FURNITURE
                "MAP" -> group.division == Division.MAP
                else -> true
            }

            matchesSearch && matchesFilter
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(
                                "MADIO Team Chat",
                                fontWeight = FontWeight.Bold,
                                style = MaterialTheme.typography.titleLarge,
                                color = Color.White
                            )
                            Spacer(modifier = Modifier.width(6.dp))
                            Surface(
                                color = Color(0x33FFFFFF),
                                shape = RoundedCornerShape(12.dp)
                            ) {
                                Row(
                                    verticalAlignment = Alignment.CenterVertically,
                                    modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                                ) {
                                    Icon(
                                        Icons.Default.Lock,
                                        contentDescription = null,
                                        tint = Color(0xFFFFD54F),
                                        modifier = Modifier.size(11.dp)
                                    )
                                    Spacer(modifier = Modifier.width(3.dp))
                                    Text("Confidential", fontSize = 10.sp, color = Color.White, fontWeight = FontWeight.SemiBold)
                                }
                            }
                        }
                        Text(
                            "Project Groups & Internal Organization Discussions",
                            style = MaterialTheme.typography.bodySmall,
                            color = Color(0xFFD1E7DD),
                            fontSize = 11.sp
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = WhatsAppDarkTeal,
                    titleContentColor = Color.White,
                    actionIconContentColor = Color.White
                ),
                actions = {
                    IconButton(
                        onClick = onCreateGroupClick,
                        modifier = Modifier.testTag("create_chat_group_top_btn")
                    ) {
                        Icon(Icons.Default.GroupAdd, contentDescription = "Create Group")
                    }
                }
            )
        },
        floatingActionButton = {
            FloatingActionButton(
                onClick = onCreateGroupClick,
                containerColor = WhatsAppGreen,
                contentColor = Color.White,
                shape = CircleShape,
                modifier = Modifier
                    .padding(bottom = 65.dp)
                    .testTag("create_group_fab")
            ) {
                Icon(Icons.Default.Chat, contentDescription = "New Project Group")
            }
        }
    ) { innerPadding ->
        Column(
            modifier = modifier
                .fillMaxSize()
                .background(Color(0xFFF7F8FA))
                .padding(innerPadding)
        ) {
            // Search Bar
            Surface(
                color = Color.White,
                tonalElevation = 2.dp,
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp)) {
                    OutlinedTextField(
                        value = searchQuery,
                        onValueChange = { searchQuery = it },
                        placeholder = { Text("Search groups, projects, or documents...", fontSize = 13.sp) },
                        leadingIcon = { Icon(Icons.Default.Search, contentDescription = null, tint = Slate400, modifier = Modifier.size(18.dp)) },
                        trailingIcon = {
                            if (searchQuery.isNotBlank()) {
                                IconButton(onClick = { searchQuery = "" }) {
                                    Icon(Icons.Default.Close, contentDescription = "Clear", modifier = Modifier.size(16.dp))
                                }
                            }
                        },
                        singleLine = true,
                        shape = RoundedCornerShape(24.dp),
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedBorderColor = WhatsAppDarkTeal,
                            unfocusedBorderColor = Color(0xFFE2E8F0),
                            unfocusedContainerColor = Color(0xFFF8FAFC),
                            focusedContainerColor = Color.White
                        ),
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(48.dp)
                            .testTag("chat_search_field")
                    )

                    Spacer(modifier = Modifier.height(8.dp))

                    // Filter Chips Row
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(6.dp)
                    ) {
                        FilterChip(
                            selected = selectedFilter == "ALL",
                            onClick = { selectedFilter = "ALL" },
                            label = { Text("All (${groups.size})", fontSize = 11.sp) },
                            colors = FilterChipDefaults.filterChipColors(
                                selectedContainerColor = WhatsAppDarkTeal,
                                selectedLabelColor = Color.White
                            )
                        )
                        FilterChip(
                            selected = selectedFilter == "LINKED",
                            onClick = { selectedFilter = "LINKED" },
                            label = {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Icon(Icons.Default.Engineering, contentDescription = null, modifier = Modifier.size(12.dp))
                                    Spacer(modifier = Modifier.width(4.dp))
                                    Text("Projects (${groups.count { it.projectId != null }})", fontSize = 11.sp)
                                }
                            },
                            colors = FilterChipDefaults.filterChipColors(
                                selectedContainerColor = WhatsAppDarkTeal,
                                selectedLabelColor = Color.White
                            )
                        )
                        FilterChip(
                            selected = selectedFilter == "CONFIDENTIAL",
                            onClick = { selectedFilter = "CONFIDENTIAL" },
                            label = {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Icon(Icons.Default.Lock, contentDescription = null, modifier = Modifier.size(11.dp))
                                    Spacer(modifier = Modifier.width(3.dp))
                                    Text("Confidential", fontSize = 11.sp)
                                }
                            },
                            colors = FilterChipDefaults.filterChipColors(
                                selectedContainerColor = Color(0xFFB45309),
                                selectedLabelColor = Color.White
                            )
                        )
                    }
                }
            }

            // Confidentiality Banner
            Surface(
                color = Color(0xFFFEF3C7),
                modifier = Modifier.fillMaxWidth()
            ) {
                Row(
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 6.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Icon(Icons.Default.Shield, contentDescription = null, tint = Color(0xFFD97706), modifier = Modifier.size(15.dp))
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(
                        "Internal Organization Network: All architectural CADs, BoQ estimates, site snags, and photos shared here remain private to MADIO staff.",
                        fontSize = 11.sp,
                        color = Color(0xFF92400E),
                        lineHeight = 14.sp
                    )
                }
            }

            // Groups LazyColumn
            LazyColumn(
                modifier = Modifier.fillMaxSize(),
                contentPadding = PaddingValues(bottom = 85.dp)
            ) {
                items(filteredGroups, key = { it.id }) { group ->
                    ChatGroupItemRow(
                        group = group,
                        onClick = { onSelectGroup(group) }
                    )
                    HorizontalDivider(color = Color(0xFFF1F5F9), thickness = 1.dp)
                }

                if (filteredGroups.isEmpty()) {
                    item {
                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(40.dp),
                            contentAlignment = Alignment.Center
                        ) {
                            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                Icon(Icons.Default.Forum, contentDescription = null, tint = Slate400, modifier = Modifier.size(48.dp))
                                Spacer(modifier = Modifier.height(8.dp))
                                Text("No chat groups found", fontWeight = FontWeight.Bold, color = Slate700)
                                Text("Create a new group linked to a project or division", fontSize = 12.sp, color = Slate500)
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun ChatGroupItemRow(
    group: ChatGroup,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .background(Color.White)
            .clickable { onClick() }
            .padding(horizontal = 16.dp, vertical = 12.dp)
            .testTag("chat_group_row_${group.id}"),
        verticalAlignment = Alignment.CenterVertically
    ) {
        // Group Avatar
        Box(
            modifier = Modifier
                .size(50.dp)
                .clip(CircleShape)
                .background(
                    when (group.groupAvatarType) {
                        "PROJECT" -> Color(0xFF0284C7)
                        "FACTORY" -> Color(0xFFD97706)
                        "MANAGEMENT" -> Color(0xFF4338CA)
                        else -> WhatsAppDarkTeal
                    }
                ),
            contentAlignment = Alignment.Center
        ) {
            Icon(
                imageVector = when (group.groupAvatarType) {
                    "PROJECT" -> Icons.Default.Apartment
                    "FACTORY" -> Icons.Default.PrecisionManufacturing
                    "MANAGEMENT" -> Icons.Default.Security
                    else -> Icons.Default.Groups
                },
                contentDescription = null,
                tint = Color.White,
                modifier = Modifier.size(26.dp)
            )
        }

        Spacer(modifier = Modifier.width(12.dp))

        // Group Information
        Column(modifier = Modifier.weight(1f)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(
                    modifier = Modifier.weight(1f),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = group.name,
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.Bold,
                        color = Slate900,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                    if (group.isConfidential) {
                        Spacer(modifier = Modifier.width(4.dp))
                        Icon(
                            Icons.Default.Lock,
                            contentDescription = "Confidential",
                            tint = Color(0xFFD97706),
                            modifier = Modifier.size(12.dp)
                        )
                    }
                }

                Text(
                    text = group.lastMessageTime,
                    fontSize = 11.sp,
                    color = if (group.unreadCount > 0) WhatsAppGreen else Slate400,
                    fontWeight = if (group.unreadCount > 0) FontWeight.Bold else FontWeight.Normal
                )
            }

            Spacer(modifier = Modifier.height(2.dp))

            // Project link badge if linked
            if (group.projectName != null || group.projectNo != null) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Surface(
                        color = Color(0xFFE0F2FE),
                        shape = RoundedCornerShape(4.dp)
                    ) {
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            modifier = Modifier.padding(horizontal = 4.dp, vertical = 1.dp)
                        ) {
                            Icon(Icons.Default.Engineering, contentDescription = null, tint = Color(0xFF0369A1), modifier = Modifier.size(10.dp))
                            Spacer(modifier = Modifier.width(3.dp))
                            Text(
                                text = group.projectNo ?: "Project",
                                fontSize = 9.sp,
                                fontWeight = FontWeight.Bold,
                                color = Color(0xFF0369A1)
                            )
                        }
                    }
                    Spacer(modifier = Modifier.width(6.dp))
                    Text(
                        text = group.projectName ?: "",
                        fontSize = 10.sp,
                        color = Slate500,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                }
                Spacer(modifier = Modifier.height(2.dp))
            }

            // Last message snippet & unread badge
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = group.lastMessage.ifBlank { "No messages yet" },
                    fontSize = 12.sp,
                    color = Slate600,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f)
                )

                if (group.unreadCount > 0) {
                    Box(
                        modifier = Modifier
                            .size(20.dp)
                            .clip(CircleShape)
                            .background(WhatsAppGreen),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            text = group.unreadCount.toString(),
                            color = Color.White,
                            fontSize = 10.sp,
                            fontWeight = FontWeight.Bold
                        )
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ChatConversationView(
    group: ChatGroup,
    linkedProject: Project?,
    messages: List<ChatMessage>,
    onBack: () -> Unit,
    onSendMessage: (String, ChatAttachment?, Boolean) -> Unit,
    onNavigateToProject: ((String) -> Unit)? = null,
    modifier: Modifier = Modifier
) {
    var inputText by remember { mutableStateOf("") }
    var isConfidentialFlag by remember { mutableStateOf(group.isConfidential) }
    var showAttachmentMenu by remember { mutableStateOf(false) }
    var showProjectDetailsDialog by remember { mutableStateOf(false) }
    var showMediaAndDocsDialog by remember { mutableStateOf(false) }
    var showGroupMembersDialog by remember { mutableStateOf(false) }

    var selectedDocumentForViewing by remember { mutableStateOf<ChatAttachment?>(null) }
    var selectedPhotoForViewing by remember { mutableStateOf<ChatAttachment?>(null) }

    val listState = rememberLazyListState()

    // Camera launcher for live site photos
    val cameraLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.TakePicturePreview()
    ) { bitmap: Bitmap? ->
        if (bitmap != null) {
            val photoAttachment = ChatAttachment(
                type = ChatAttachmentType.IMAGE,
                title = "Live_Site_Capture_${System.currentTimeMillis().toString().takeLast(4)}.jpg",
                subtitle = "Captured via Live Field Camera",
                fileSize = "2.1 MB",
                extension = "JPG",
                localBitmap = bitmap,
                documentContent = "Live photo taken at site during engineering supervision."
            )
            onSendMessage("Live site photo captured", photoAttachment, isConfidentialFlag)
        }
    }

    // Scroll to latest message on new message
    LaunchedEffect(messages.size) {
        if (messages.isNotEmpty()) {
            listState.animateScrollToItem(messages.size - 1)
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                navigationIcon = {
                    IconButton(
                        onClick = onBack,
                        modifier = Modifier.testTag("chat_back_button")
                    ) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back", tint = Color.White)
                    }
                },
                title = {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        modifier = Modifier
                            .clickable { showGroupMembersDialog = true }
                            .padding(vertical = 4.dp)
                    ) {
                        Box(
                            modifier = Modifier
                                .size(38.dp)
                                .clip(CircleShape)
                                .background(Color.White.copy(alpha = 0.2f)),
                            contentAlignment = Alignment.Center
                        ) {
                            Icon(
                                imageVector = when (group.groupAvatarType) {
                                    "PROJECT" -> Icons.Default.Apartment
                                    "FACTORY" -> Icons.Default.PrecisionManufacturing
                                    "MANAGEMENT" -> Icons.Default.Security
                                    else -> Icons.Default.Groups
                                },
                                contentDescription = null,
                                tint = Color.White,
                                modifier = Modifier.size(20.dp)
                            )
                        }

                        Spacer(modifier = Modifier.width(8.dp))

                        Column {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text(
                                    text = group.name,
                                    style = MaterialTheme.typography.titleSmall,
                                    fontWeight = FontWeight.Bold,
                                    color = Color.White,
                                    maxLines = 1,
                                    overflow = TextOverflow.Ellipsis
                                )
                                if (group.isConfidential) {
                                    Spacer(modifier = Modifier.width(4.dp))
                                    Icon(
                                        Icons.Default.Lock,
                                        contentDescription = "Confidential",
                                        tint = Color(0xFFFFD54F),
                                        modifier = Modifier.size(11.dp)
                                    )
                                }
                            }
                            Text(
                                text = group.members.joinToString(", ") { it.name.substringBefore(" ") },
                                style = MaterialTheme.typography.bodySmall,
                                color = Color(0xFFD1E7DD),
                                fontSize = 10.sp,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis
                            )
                        }
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = WhatsAppDarkTeal,
                    titleContentColor = Color.White,
                    actionIconContentColor = Color.White
                ),
                actions = {
                    if (linkedProject != null) {
                        IconButton(
                            onClick = { showProjectDetailsDialog = true },
                            modifier = Modifier.testTag("chat_linked_project_btn")
                        ) {
                            Icon(Icons.Default.Engineering, contentDescription = "Project Hub", tint = Color.White)
                        }
                    }
                    IconButton(
                        onClick = { showMediaAndDocsDialog = true },
                        modifier = Modifier.testTag("chat_media_docs_btn")
                    ) {
                        Icon(Icons.Default.FolderZip, contentDescription = "Shared Docs & Media", tint = Color.White)
                    }
                }
            )
        },
        bottomBar = {
            // WhatsApp Style Input Bar
            Surface(
                color = Color(0xFFF0F2F5),
                tonalElevation = 6.dp,
                modifier = Modifier
                    .fillMaxWidth()
                    .imePadding()
            ) {
                Column {
                    // Confidential mode toggle indicator
                    if (isConfidentialFlag) {
                        Surface(
                            color = Color(0xFFFEF3C7),
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Row(
                                modifier = Modifier.padding(horizontal = 16.dp, vertical = 3.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Icon(Icons.Default.Lock, contentDescription = null, tint = Color(0xFFD97706), modifier = Modifier.size(12.dp))
                                Spacer(modifier = Modifier.width(4.dp))
                                Text("Confidential Mode Active • Internal MADIO Organization Only", fontSize = 10.sp, color = Color(0xFF92400E), fontWeight = FontWeight.SemiBold)
                            }
                        }
                    }

                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 8.dp, vertical = 6.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        // Input box pill
                        Surface(
                            shape = RoundedCornerShape(24.dp),
                            color = Color.White,
                            modifier = Modifier.weight(1f)
                        ) {
                            Row(
                                modifier = Modifier
                                    .padding(horizontal = 8.dp, vertical = 2.dp)
                                    .fillMaxWidth(),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                // Confidential Lock Toggle
                                IconButton(
                                    onClick = { isConfidentialFlag = !isConfidentialFlag },
                                    modifier = Modifier.size(36.dp)
                                ) {
                                    Icon(
                                        Icons.Default.Lock,
                                        contentDescription = "Toggle Confidential",
                                        tint = if (isConfidentialFlag) Color(0xFFD97706) else Slate400,
                                        modifier = Modifier.size(18.dp)
                                    )
                                }

                                OutlinedTextField(
                                    value = inputText,
                                    onValueChange = { inputText = it },
                                    placeholder = { Text("Message...", fontSize = 14.sp) },
                                    colors = OutlinedTextFieldDefaults.colors(
                                        unfocusedBorderColor = Color.Transparent,
                                        focusedBorderColor = Color.Transparent,
                                        unfocusedContainerColor = Color.Transparent,
                                        focusedContainerColor = Color.Transparent
                                    ),
                                    maxLines = 4,
                                    modifier = Modifier
                                        .weight(1f)
                                        .testTag("chat_input_text")
                                )

                                // Attachment Paperclip
                                IconButton(
                                    onClick = { showAttachmentMenu = true },
                                    modifier = Modifier.size(36.dp).testTag("chat_attachment_btn")
                                ) {
                                    Icon(Icons.Default.AttachFile, contentDescription = "Attach", tint = Slate500, modifier = Modifier.size(20.dp))
                                }

                                // Direct Live Camera
                                IconButton(
                                    onClick = { cameraLauncher.launch(null) },
                                    modifier = Modifier.size(36.dp).testTag("chat_camera_btn")
                                ) {
                                    Icon(Icons.Default.CameraAlt, contentDescription = "Camera", tint = Slate500, modifier = Modifier.size(20.dp))
                                }
                            }
                        }

                        Spacer(modifier = Modifier.width(6.dp))

                        // Circular Send FAB
                        FloatingActionButton(
                            onClick = {
                                if (inputText.isNotBlank()) {
                                    onSendMessage(inputText.trim(), null, isConfidentialFlag)
                                    inputText = ""
                                }
                            },
                            containerColor = WhatsAppGreen,
                            contentColor = Color.White,
                            shape = CircleShape,
                            modifier = Modifier
                                .size(46.dp)
                                .testTag("chat_send_fab")
                        ) {
                            Icon(Icons.Default.Send, contentDescription = "Send", modifier = Modifier.size(20.dp))
                        }
                    }
                }
            }
        }
    ) { innerPadding ->
        Box(
            modifier = modifier
                .fillMaxSize()
                .background(WhatsAppWallpaperBg)
                .padding(innerPadding)
        ) {
            Column(modifier = Modifier.fillMaxSize()) {
                // Top Linked Project Context Banner (if available)
                if (linkedProject != null) {
                    Surface(
                        color = Color(0xFFF8FAFC),
                        tonalElevation = 2.dp,
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable { showProjectDetailsDialog = true }
                    ) {
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(horizontal = 14.dp, vertical = 6.dp),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Icon(Icons.Default.Apartment, contentDescription = null, tint = AuraBlue, modifier = Modifier.size(15.dp))
                                Spacer(modifier = Modifier.width(6.dp))
                                Column {
                                    Row(verticalAlignment = Alignment.CenterVertically) {
                                        Text(linkedProject.projectNo, fontWeight = FontWeight.Bold, fontSize = 11.sp, color = AuraBlue)
                                        Spacer(modifier = Modifier.width(4.dp))
                                        Text("• ${linkedProject.customerName}", fontSize = 11.sp, fontWeight = FontWeight.Medium, color = Slate800)
                                    }
                                    Text(
                                        "Stage: ${linkedProject.stage} (${linkedProject.completionPct}%) • Assigned: ${linkedProject.assignedEngineer}",
                                        fontSize = 10.sp,
                                        color = Slate500
                                    )
                                }
                            }

                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text("View Hub", fontSize = 10.sp, fontWeight = FontWeight.Bold, color = AuraBlue)
                                Icon(Icons.Default.ChevronRight, contentDescription = null, tint = AuraBlue, modifier = Modifier.size(16.dp))
                            }
                        }
                    }
                }

                // Chat Messages LazyColumn
                LazyColumn(
                    state = listState,
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(horizontal = 12.dp),
                    contentPadding = PaddingValues(top = 10.dp, bottom = 10.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    items(messages, key = { it.id }) { message ->
                        if (message.isSystemNotice) {
                            SystemNoticeBubble(message.text)
                        } else {
                            ChatMessageBubble(
                                message = message,
                                onDocumentClick = { doc -> selectedDocumentForViewing = doc },
                                onPhotoClick = { photo -> selectedPhotoForViewing = photo }
                            )
                        }
                    }
                }
            }
        }
    }

    // Attachment Chooser Dialog
    if (showAttachmentMenu) {
        AttachmentChooserDialog(
            onDismiss = { showAttachmentMenu = false },
            onCameraSelect = {
                showAttachmentMenu = false
                cameraLauncher.launch(null)
            },
            onPresetPhotoSelect = { photoTitle, photoSubtitle, specContent ->
                showAttachmentMenu = false
                val attachment = ChatAttachment(
                    type = ChatAttachmentType.IMAGE,
                    title = photoTitle,
                    subtitle = photoSubtitle,
                    fileSize = "1.9 MB",
                    extension = "JPG",
                    documentContent = specContent
                )
                onSendMessage(photoSubtitle, attachment, isConfidentialFlag)
            },
            onDocumentSelect = { docTitle, docExt, docSize, docContent ->
                showAttachmentMenu = false
                val attachment = ChatAttachment(
                    type = ChatAttachmentType.DOCUMENT,
                    title = docTitle,
                    subtitle = "Project Spec & Technical Sheet",
                    fileSize = docSize,
                    extension = docExt,
                    documentContent = docContent
                )
                onSendMessage("Shared document: $docTitle", attachment, isConfidentialFlag)
            },
            onVoiceNoteSelect = { voiceTitle, duration ->
                showAttachmentMenu = false
                val attachment = ChatAttachment(
                    type = ChatAttachmentType.VOICE,
                    title = voiceTitle,
                    subtitle = "Audio Note ($duration)",
                    fileSize = "420 KB",
                    extension = "AAC",
                    documentContent = "Voice memo from site engineer: Shutter alignment in master bedroom complete, need 2 extra soft-close hinges."
                )
                onSendMessage("Voice note: $voiceTitle", attachment, isConfidentialFlag)
            }
        )
    }

    // Document Viewer Dialog
    selectedDocumentForViewing?.let { doc ->
        DocumentViewerDialog(
            document = doc,
            onDismiss = { selectedDocumentForViewing = null }
        )
    }

    // Photo Zoom Viewer Dialog
    selectedPhotoForViewing?.let { photo ->
        PhotoViewerDialog(
            photo = photo,
            onDismiss = { selectedPhotoForViewing = null }
        )
    }

    // Project Details Dialog
    if (showProjectDetailsDialog && linkedProject != null) {
        LinkedProjectSummaryDialog(
            project = linkedProject,
            onDismiss = { showProjectDetailsDialog = false },
            onOpenProjectScreen = {
                showProjectDetailsDialog = false
                onNavigateToProject?.invoke(linkedProject.id)
            }
        )
    }

    // Media & Documents Drawer/Dialog
    if (showMediaAndDocsDialog) {
        MediaAndDocsOverviewDialog(
            groupName = group.name,
            messages = messages,
            onDismiss = { showMediaAndDocsDialog = false },
            onOpenDocument = { doc ->
                showMediaAndDocsDialog = false
                selectedDocumentForViewing = doc
            },
            onOpenPhoto = { photo ->
                showMediaAndDocsDialog = false
                selectedPhotoForViewing = photo
            }
        )
    }

    // Group Members Dialog
    if (showGroupMembersDialog) {
        GroupMembersDialog(
            group = group,
            onDismiss = { showGroupMembersDialog = false }
        )
    }
}

@Composable
fun SystemNoticeBubble(text: String) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp),
        contentAlignment = Alignment.Center
    ) {
        Surface(
            color = WhatsAppSystemChip,
            shape = RoundedCornerShape(8.dp),
            shadowElevation = 0.5.dp
        ) {
            Row(
                modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Icon(Icons.Default.Lock, contentDescription = null, tint = Color(0xFF856404), modifier = Modifier.size(12.dp))
                Spacer(modifier = Modifier.width(6.dp))
                Text(
                    text = text,
                    fontSize = 11.sp,
                    color = Color(0xFF856404),
                    lineHeight = 15.sp,
                    fontWeight = FontWeight.Medium
                )
            }
        }
    }
}

@Composable
fun ChatMessageBubble(
    message: ChatMessage,
    onDocumentClick: (ChatAttachment) -> Unit,
    onPhotoClick: (ChatAttachment) -> Unit,
    modifier: Modifier = Modifier
) {
    val isMe = message.isFromMe

    Row(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = if (isMe) Arrangement.End else Arrangement.Start
    ) {
        Surface(
            color = if (isMe) WhatsAppOutgoingBubble else WhatsAppIncomingBubble,
            shape = RoundedCornerShape(
                topStart = 12.dp,
                topEnd = 12.dp,
                bottomStart = if (isMe) 12.dp else 2.dp,
                bottomEnd = if (isMe) 2.dp else 12.dp
            ),
            shadowElevation = 1.dp,
            modifier = Modifier
                .widthIn(max = 310.dp)
                .testTag("chat_bubble_${message.id}")
        ) {
            Column(modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp)) {
                // Sender info (for incoming messages)
                if (!isMe) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            text = message.senderName,
                            fontSize = 11.sp,
                            fontWeight = FontWeight.Bold,
                            color = WhatsAppDarkTeal
                        )
                        Surface(
                            color = Color(0xFFE0F2FE),
                            shape = RoundedCornerShape(4.dp)
                        ) {
                            Text(
                                text = message.senderRole,
                                fontSize = 9.sp,
                                color = Color(0xFF0369A1),
                                fontWeight = FontWeight.SemiBold,
                                modifier = Modifier.padding(horizontal = 4.dp, vertical = 1.dp)
                            )
                        }
                    }
                    Spacer(modifier = Modifier.height(2.dp))
                }

                // Confidential Tag
                if (message.isConfidential) {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        modifier = Modifier.padding(bottom = 4.dp)
                    ) {
                        Icon(Icons.Default.Lock, contentDescription = null, tint = Color(0xFFD97706), modifier = Modifier.size(10.dp))
                        Spacer(modifier = Modifier.width(3.dp))
                        Text(
                            "Strictly Confidential",
                            fontSize = 9.sp,
                            fontWeight = FontWeight.Bold,
                            color = Color(0xFFB45309)
                        )
                    }
                }

                // Attachment Preview (Image, Document, Voice)
                message.attachment?.let { att ->
                    when (att.type) {
                        ChatAttachmentType.IMAGE -> {
                            ImageAttachmentCard(
                                attachment = att,
                                onClick = { onPhotoClick(att) }
                            )
                            Spacer(modifier = Modifier.height(4.dp))
                        }
                        ChatAttachmentType.DOCUMENT -> {
                            DocumentAttachmentCard(
                                attachment = att,
                                onClick = { onDocumentClick(att) }
                            )
                            Spacer(modifier = Modifier.height(4.dp))
                        }
                        ChatAttachmentType.VOICE -> {
                            VoiceAttachmentCard(attachment = att)
                            Spacer(modifier = Modifier.height(4.dp))
                        }
                        else -> {}
                    }
                }

                // Message Text
                if (message.text.isNotBlank()) {
                    Text(
                        text = message.text,
                        fontSize = 13.sp,
                        color = Color(0xFF1E293B),
                        lineHeight = 18.sp
                    )
                }

                Spacer(modifier = Modifier.height(2.dp))

                // Timestamp and Read Receipts
                Row(
                    modifier = Modifier.align(Alignment.End),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = message.timestamp,
                        fontSize = 10.sp,
                        color = Color(0xFF64748B)
                    )
                    if (isMe) {
                        Spacer(modifier = Modifier.width(4.dp))
                        Icon(
                            imageVector = Icons.Default.DoneAll,
                            contentDescription = "Read",
                            tint = WhatsAppBlueTicks,
                            modifier = Modifier.size(13.dp)
                        )
                    }
                }
            }
        }
    }
}

@Composable
fun ImageAttachmentCard(
    attachment: ChatAttachment,
    onClick: () -> Unit
) {
    Card(
        shape = RoundedCornerShape(8.dp),
        colors = CardDefaults.cardColors(containerColor = Color(0xFF0F172A)),
        modifier = Modifier
            .fillMaxWidth()
            .clickable { onClick() }
    ) {
        Column {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(140.dp)
                    .background(Color(0xFF1E293B)),
                contentAlignment = Alignment.Center
            ) {
                if (attachment.localBitmap != null) {
                    androidx.compose.foundation.Image(
                        bitmap = attachment.localBitmap.asImageBitmap(),
                        contentDescription = attachment.title,
                        modifier = Modifier.fillMaxSize()
                    )
                } else {
                    // Stylized architectural photo card
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        modifier = Modifier.padding(16.dp)
                    ) {
                        Icon(
                            Icons.Default.PhotoLibrary,
                            contentDescription = null,
                            tint = Color(0xFF38BDF8),
                            modifier = Modifier.size(36.dp)
                        )
                        Spacer(modifier = Modifier.height(6.dp))
                        Text(
                            attachment.title,
                            color = Color.White,
                            fontSize = 11.sp,
                            fontWeight = FontWeight.Bold,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis
                        )
                        Text(
                            attachment.subtitle,
                            color = Color(0xFF94A3B8),
                            fontSize = 10.sp
                        )
                    }
                }

                // Tap to zoom chip
                Surface(
                    color = Color.Black.copy(alpha = 0.6f),
                    shape = RoundedCornerShape(12.dp),
                    modifier = Modifier
                        .align(Alignment.BottomEnd)
                        .padding(6.dp)
                ) {
                    Row(
                        modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(Icons.Default.Fullscreen, contentDescription = null, tint = Color.White, modifier = Modifier.size(12.dp))
                        Spacer(modifier = Modifier.width(2.dp))
                        Text("View Photo", color = Color.White, fontSize = 9.sp)
                    }
                }
            }

            Surface(
                color = Color(0xFF0F172A),
                modifier = Modifier.fillMaxWidth()
            ) {
                Row(
                    modifier = Modifier.padding(horizontal = 8.dp, vertical = 6.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        attachment.title,
                        fontSize = 10.sp,
                        color = Color.White,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f)
                    )
                    Text(
                        attachment.fileSize,
                        fontSize = 9.sp,
                        color = Color(0xFF94A3B8)
                    )
                }
            }
        }
    }
}

@Composable
fun DocumentAttachmentCard(
    attachment: ChatAttachment,
    onClick: () -> Unit
) {
    Card(
        shape = RoundedCornerShape(8.dp),
        colors = CardDefaults.cardColors(containerColor = Color(0xFFF1F5F9)),
        modifier = Modifier
            .fillMaxWidth()
            .clickable { onClick() }
    ) {
        Row(
            modifier = Modifier.padding(8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // File badge
            Box(
                modifier = Modifier
                    .size(40.dp)
                    .clip(RoundedCornerShape(6.dp))
                    .background(
                        when (attachment.extension.uppercase()) {
                            "PDF" -> Color(0xFFEF4444)
                            "XLSX", "XLS" -> Color(0xFF10B981)
                            "DWG", "CAD" -> Color(0xFF3B82F6)
                            else -> Color(0xFF6B7280)
                        }
                    ),
                contentAlignment = Alignment.Center
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Icon(
                        Icons.Default.Description,
                        contentDescription = null,
                        tint = Color.White,
                        modifier = Modifier.size(18.dp)
                    )
                    Text(
                        text = attachment.extension.uppercase(),
                        color = Color.White,
                        fontSize = 8.sp,
                        fontWeight = FontWeight.Bold
                    )
                }
            }

            Spacer(modifier = Modifier.width(10.dp))

            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = attachment.title,
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Bold,
                    color = Slate900,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
                Text(
                    text = "${attachment.fileSize} • Tap to view document",
                    fontSize = 10.sp,
                    color = Slate500
                )
            }

            Icon(
                Icons.Default.OpenInNew,
                contentDescription = "Open",
                tint = WhatsAppDarkTeal,
                modifier = Modifier.size(18.dp)
            )
        }
    }
}

@Composable
fun VoiceAttachmentCard(attachment: ChatAttachment) {
    var isPlaying by remember { mutableStateOf(false) }

    Surface(
        color = Color(0xFFF1F5F9),
        shape = RoundedCornerShape(8.dp),
        modifier = Modifier.fillMaxWidth()
    ) {
        Row(
            modifier = Modifier.padding(8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            IconButton(
                onClick = { isPlaying = !isPlaying },
                modifier = Modifier
                    .size(36.dp)
                    .clip(CircleShape)
                    .background(WhatsAppDarkTeal)
            ) {
                Icon(
                    if (isPlaying) Icons.Default.Pause else Icons.Default.PlayArrow,
                    contentDescription = if (isPlaying) "Pause" else "Play",
                    tint = Color.White,
                    modifier = Modifier.size(20.dp)
                )
            }

            Spacer(modifier = Modifier.width(8.dp))

            Column(modifier = Modifier.weight(1f)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Text(attachment.title, fontSize = 11.sp, fontWeight = FontWeight.SemiBold, color = Slate800)
                    Text(attachment.subtitle, fontSize = 10.sp, color = Slate500)
                }

                Spacer(modifier = Modifier.height(4.dp))

                // Simulated audio waveform
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(2.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    listOf(4, 10, 16, 22, 14, 8, 18, 24, 16, 12, 20, 26, 15, 8, 12, 18, 14, 6).forEach { height ->
                        Box(
                            modifier = Modifier
                                .width(3.dp)
                                .height(height.dp)
                                .background(if (isPlaying) WhatsAppGreen else Color(0xFF94A3B8), RoundedCornerShape(1.dp))
                        )
                    }
                }
            }
        }
    }
}

@Composable
fun AttachmentChooserDialog(
    onDismiss: () -> Unit,
    onCameraSelect: () -> Unit,
    onPresetPhotoSelect: (String, String, String) -> Unit,
    onDocumentSelect: (String, String, String, String) -> Unit,
    onVoiceNoteSelect: (String, String) -> Unit
) {
    Dialog(onDismissRequest = onDismiss) {
        Card(
            shape = RoundedCornerShape(20.dp),
            colors = CardDefaults.cardColors(containerColor = Color.White),
            modifier = Modifier.fillMaxWidth()
        ) {
            Column(modifier = Modifier.padding(20.dp)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("Share to Project Group", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium, color = Slate900)
                    IconButton(onClick = onDismiss, modifier = Modifier.size(24.dp)) {
                        Icon(Icons.Default.Close, contentDescription = "Close", tint = Slate400)
                    }
                }

                Spacer(modifier = Modifier.height(14.dp))

                Text("SITE PICTURES & MEDIA", fontSize = 10.sp, fontWeight = FontWeight.Bold, color = Slate400)
                Spacer(modifier = Modifier.height(8.dp))

                // Camera & Preset photos
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    AttachmentOptionCard(
                        icon = Icons.Default.CameraAlt,
                        label = "Take Live\nSite Photo",
                        backgroundColor = Color(0xFFEF4444),
                        onClick = onCameraSelect,
                        modifier = Modifier.weight(1f)
                    )

                    AttachmentOptionCard(
                        icon = Icons.Default.Carpenter,
                        label = "Woodwork\nFramework",
                        backgroundColor = Color(0xFFD97706),
                        onClick = {
                            onPresetPhotoSelect(
                                "Wardrobe_MarinePly_Framework_Inspection.jpg",
                                "Carcass & plinth level inspection for master bedroom",
                                "Inspected 18mm Century 710 marine ply carcass leveling. Tolerances verified within 1.5mm."
                            )
                        },
                        modifier = Modifier.weight(1f)
                    )

                    AttachmentOptionCard(
                        icon = Icons.Default.FormatPaint,
                        label = "MAP Paint\nCoat Swatch",
                        backgroundColor = Color(0xFF059669),
                        onClick = {
                            onPresetPhotoSelect(
                                "MAP_Venetian_Stucco_Coat2_Texture.jpg",
                                "Second coat Venetian stucco with beeswax burnishing",
                                "Atrium wall finish coat 2 inspection under natural daylight."
                            )
                        },
                        modifier = Modifier.weight(1f)
                    )
                }

                Spacer(modifier = Modifier.height(16.dp))
                Text("DOCUMENTS & SPECIFICATIONS", fontSize = 10.sp, fontWeight = FontWeight.Bold, color = Slate400)
                Spacer(modifier = Modifier.height(8.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    AttachmentOptionCard(
                        icon = Icons.Default.PictureAsPdf,
                        label = "CAD Elevation\nDrawing (PDF)",
                        backgroundColor = Color(0xFFDC2626),
                        onClick = {
                            onDocumentSelect(
                                "Master_Wardrobe_Elevations_Rev5.pdf",
                                "PDF",
                                "3.2 MB",
                                "ARCHITECTURAL SPECIFICATION REV 5:\n- Clear height: 2800mm\n- Shutter profiles: Hafele Aluflex concealed\n- Internal LED strip routing with aluminum channel heat-sinks\n- Soft-close hinges: Blum Clip Top 110 deg"
                            )
                        },
                        modifier = Modifier.weight(1f)
                    )

                    AttachmentOptionCard(
                        icon = Icons.Default.TableChart,
                        label = "Hardware\nBoQ (Excel)",
                        backgroundColor = Color(0xFF16A34A),
                        onClick = {
                            onDocumentSelect(
                                "Project_Hardware_BoQ_Dispatched.xlsx",
                                "XLSX",
                                "1.6 MB",
                                "HARDWARE BILL OF QUANTITIES:\n1. 24x Blum 110 deg hinges - ₹11,520\n2. 8x Legrabox 500mm drawer runners - ₹33,600\n3. 1x Hafele Sliding System - ₹22,400\nTotal Dispatched: ₹67,520"
                            )
                        },
                        modifier = Modifier.weight(1f)
                    )

                    AttachmentOptionCard(
                        icon = Icons.Default.Mic,
                        label = "Engineer\nVoice Memo",
                        backgroundColor = Color(0xFF2563EB),
                        onClick = {
                            onVoiceNoteSelect("Site Engineer Audio Note #4", "0:45")
                        },
                        modifier = Modifier.weight(1f)
                    )
                }
            }
        }
    }
}

@Composable
fun AttachmentOptionCard(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    label: String,
    backgroundColor: Color,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    Surface(
        color = Color(0xFFF8FAFC),
        shape = RoundedCornerShape(12.dp),
        border = androidx.compose.foundation.BorderStroke(1.dp, Color(0xFFE2E8F0)),
        modifier = modifier.clickable { onClick() }
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            modifier = Modifier.padding(horizontal = 4.dp, vertical = 10.dp)
        ) {
            Box(
                modifier = Modifier
                    .size(36.dp)
                    .clip(CircleShape)
                    .background(backgroundColor),
                contentAlignment = Alignment.Center
            ) {
                Icon(icon, contentDescription = null, tint = Color.White, modifier = Modifier.size(18.dp))
            }
            Spacer(modifier = Modifier.height(6.dp))
            Text(
                text = label,
                fontSize = 10.sp,
                fontWeight = FontWeight.SemiBold,
                color = Slate800,
                textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                lineHeight = 13.sp
            )
        }
    }
}

@Composable
fun DocumentViewerDialog(
    document: ChatAttachment,
    onDismiss: () -> Unit
) {
    Dialog(onDismissRequest = onDismiss) {
        Card(
            shape = RoundedCornerShape(16.dp),
            colors = CardDefaults.cardColors(containerColor = Color.White),
            modifier = Modifier
                .fillMaxWidth()
                .fillMaxHeight(0.85f)
        ) {
            Column(modifier = Modifier.padding(20.dp)) {
                // Header
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(
                            modifier = Modifier
                                .size(32.dp)
                                .clip(RoundedCornerShape(6.dp))
                                .background(
                                    when (document.extension.uppercase()) {
                                        "PDF" -> Color(0xFFEF4444)
                                        "XLSX" -> Color(0xFF10B981)
                                        else -> Color(0xFF3B82F6)
                                    }
                                ),
                            contentAlignment = Alignment.Center
                        ) {
                            Text(document.extension.uppercase(), color = Color.White, fontSize = 10.sp, fontWeight = FontWeight.Bold)
                        }
                        Spacer(modifier = Modifier.width(8.dp))
                        Column {
                            Text(document.title, fontWeight = FontWeight.Bold, fontSize = 13.sp, color = Slate900, maxLines = 1, overflow = TextOverflow.Ellipsis)
                            Text("${document.fileSize} • Verified MADIO Document", fontSize = 10.sp, color = Slate500)
                        }
                    }

                    IconButton(onClick = onDismiss) {
                        Icon(Icons.Default.Close, contentDescription = "Close", tint = Slate400)
                    }
                }

                Spacer(modifier = Modifier.height(12.dp))
                HorizontalDivider(color = Slate200)
                Spacer(modifier = Modifier.height(12.dp))

                // Confidential stamp
                Surface(
                    color = Color(0xFFFEF3C7),
                    shape = RoundedCornerShape(8.dp),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Row(
                        modifier = Modifier.padding(8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(Icons.Default.Shield, contentDescription = null, tint = Color(0xFFD97706), modifier = Modifier.size(16.dp))
                        Spacer(modifier = Modifier.width(6.dp))
                        Text(
                            "CONFIDENTIAL INTERNAL DOCUMENT — Do not circulate outside MADIO Group.",
                            fontSize = 10.sp,
                            fontWeight = FontWeight.Bold,
                            color = Color(0xFF92400E)
                        )
                    }
                }

                Spacer(modifier = Modifier.height(12.dp))

                // Document content preview
                Surface(
                    color = Color(0xFFF8FAFC),
                    shape = RoundedCornerShape(8.dp),
                    border = androidx.compose.foundation.BorderStroke(1.dp, Color(0xFFE2E8F0)),
                    modifier = Modifier
                        .fillMaxWidth()
                        .weight(1f)
                ) {
                    LazyColumn(modifier = Modifier.padding(14.dp)) {
                        item {
                            Text(
                                text = document.documentContent.ifBlank {
                                    "No readable text stream. File format ${document.extension} is encoded with digital CAD vectors."
                                },
                                fontFamily = FontFamily.Monospace,
                                fontSize = 11.sp,
                                color = Slate800,
                                lineHeight = 16.sp
                            )
                        }
                    }
                }

                Spacer(modifier = Modifier.height(14.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("Status: Sealed & Verified", fontSize = 11.sp, color = SuccessGreen, fontWeight = FontWeight.Bold)

                    Button(
                        onClick = onDismiss,
                        colors = ButtonDefaults.buttonColors(containerColor = WhatsAppDarkTeal),
                        shape = RoundedCornerShape(8.dp)
                    ) {
                        Text("Done")
                    }
                }
            }
        }
    }
}

@Composable
fun PhotoViewerDialog(
    photo: ChatAttachment,
    onDismiss: () -> Unit
) {
    Dialog(onDismissRequest = onDismiss) {
        Card(
            shape = RoundedCornerShape(16.dp),
            colors = CardDefaults.cardColors(containerColor = Color(0xFF0F172A)),
            modifier = Modifier
                .fillMaxWidth()
                .fillMaxHeight(0.8f)
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column {
                        Text(photo.title, fontWeight = FontWeight.Bold, color = Color.White, fontSize = 13.sp)
                        Text(photo.subtitle, color = Color(0xFF94A3B8), fontSize = 10.sp)
                    }
                    IconButton(onClick = onDismiss) {
                        Icon(Icons.Default.Close, contentDescription = "Close", tint = Color.White)
                    }
                }

                Spacer(modifier = Modifier.height(12.dp))

                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .weight(1f)
                        .clip(RoundedCornerShape(8.dp))
                        .background(Color(0xFF1E293B)),
                    contentAlignment = Alignment.Center
                ) {
                    if (photo.localBitmap != null) {
                        androidx.compose.foundation.Image(
                            bitmap = photo.localBitmap.asImageBitmap(),
                            contentDescription = photo.title,
                            modifier = Modifier.fillMaxSize()
                        )
                    } else {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Icon(Icons.Default.Image, contentDescription = null, tint = Color(0xFF38BDF8), modifier = Modifier.size(64.dp))
                            Spacer(modifier = Modifier.height(12.dp))
                            Text(photo.title, color = Color.White, fontWeight = FontWeight.Bold)
                            Text("Full resolution site photography verified", color = Color(0xFF94A3B8), fontSize = 11.sp)
                        }
                    }
                }

                Spacer(modifier = Modifier.height(12.dp))

                Surface(
                    color = Color(0xFF1E293B),
                    shape = RoundedCornerShape(8.dp),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(modifier = Modifier.padding(10.dp)) {
                        Text("Site Inspection Remarks:", color = Color(0xFF38BDF8), fontSize = 10.sp, fontWeight = FontWeight.Bold)
                        Spacer(modifier = Modifier.height(2.dp))
                        Text(photo.documentContent, color = Color.White, fontSize = 11.sp)
                    }
                }

                Spacer(modifier = Modifier.height(12.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.End
                ) {
                    Button(
                        onClick = onDismiss,
                        colors = ButtonDefaults.buttonColors(containerColor = WhatsAppGreen),
                        shape = RoundedCornerShape(8.dp)
                    ) {
                        Text("Close View")
                    }
                }
            }
        }
    }
}

@Composable
fun LinkedProjectSummaryDialog(
    project: Project,
    onDismiss: () -> Unit,
    onOpenProjectScreen: () -> Unit
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
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(project.projectNo, fontWeight = FontWeight.Bold, color = AuraBlue, fontSize = 13.sp)
                            Spacer(modifier = Modifier.width(6.dp))
                            DivisionBadge(project.division)
                        }
                        Text(project.customerName, fontWeight = FontWeight.Bold, fontSize = 16.sp, color = Slate900)
                    }
                    IconButton(onClick = onDismiss) {
                        Icon(Icons.Default.Close, contentDescription = "Close", tint = Slate400)
                    }
                }

                Spacer(modifier = Modifier.height(12.dp))
                HorizontalDivider(color = Slate200)
                Spacer(modifier = Modifier.height(12.dp))

                Text("Site Address: ${project.siteAddress}", fontSize = 12.sp, color = Slate700)
                Text("Assigned Site Engineer: ${project.assignedEngineer}", fontSize = 12.sp, color = Slate700)
                Text("Target Handover: ${project.targetDate}", fontSize = 12.sp, color = Slate700)

                Spacer(modifier = Modifier.height(12.dp))

                // Progress Bar
                Text("Execution Progress (${project.completionPct}%)", fontWeight = FontWeight.Bold, fontSize = 11.sp, color = Slate800)
                Spacer(modifier = Modifier.height(4.dp))
                LinearProgressIndicator(
                    progress = { project.completionPct / 100f },
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(8.dp)
                        .clip(RoundedCornerShape(4.dp)),
                    color = if (project.completionPct >= 100) SuccessGreen else AuraBlue,
                    trackColor = Slate100
                )

                Spacer(modifier = Modifier.height(14.dp))

                // Financial Overview
                Surface(
                    color = Color(0xFFF8FAFC),
                    shape = RoundedCornerShape(8.dp),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Row(
                        modifier = Modifier.padding(12.dp),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Column {
                            Text("Contract Value", fontSize = 10.sp, color = Slate500)
                            Text(formatInr(project.contractValue), fontWeight = FontWeight.Bold, fontSize = 12.sp, color = Slate900)
                        }
                        Column {
                            Text("Paid Amount", fontSize = 10.sp, color = Slate500)
                            Text(formatInr(project.paidAmount), fontWeight = FontWeight.Bold, fontSize = 12.sp, color = SuccessGreen)
                        }
                        Column {
                            Text("Stage", fontSize = 10.sp, color = Slate500)
                            Text(project.stage, fontWeight = FontWeight.Bold, fontSize = 12.sp, color = AuraBlue)
                        }
                    }
                }

                Spacer(modifier = Modifier.height(16.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.End
                ) {
                    TextButton(onClick = onDismiss) {
                        Text("Close", color = Slate600)
                    }
                    Spacer(modifier = Modifier.width(8.dp))
                    Button(
                        onClick = onOpenProjectScreen,
                        colors = ButtonDefaults.buttonColors(containerColor = AuraBlue)
                    ) {
                        Icon(Icons.Default.Engineering, contentDescription = null, modifier = Modifier.size(16.dp))
                        Spacer(modifier = Modifier.width(4.dp))
                        Text("Open Project Screen")
                    }
                }
            }
        }
    }
}

@Composable
fun MediaAndDocsOverviewDialog(
    groupName: String,
    messages: List<ChatMessage>,
    onDismiss: () -> Unit,
    onOpenDocument: (ChatAttachment) -> Unit,
    onOpenPhoto: (ChatAttachment) -> Unit
) {
    val documents = remember(messages) {
        messages.mapNotNull { it.attachment }.filter { it.type == ChatAttachmentType.DOCUMENT }
    }
    val photos = remember(messages) {
        messages.mapNotNull { it.attachment }.filter { it.type == ChatAttachmentType.IMAGE }
    }

    Dialog(onDismissRequest = onDismiss) {
        Card(
            shape = RoundedCornerShape(16.dp),
            colors = CardDefaults.cardColors(containerColor = Color.White),
            modifier = Modifier
                .fillMaxWidth()
                .fillMaxHeight(0.8f)
        ) {
            Column(modifier = Modifier.padding(18.dp)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column {
                        Text("Shared Media & Documents", fontWeight = FontWeight.Bold, fontSize = 14.sp, color = Slate900)
                        Text(groupName, fontSize = 11.sp, color = Slate500)
                    }
                    IconButton(onClick = onDismiss) {
                        Icon(Icons.Default.Close, contentDescription = "Close", tint = Slate400)
                    }
                }

                Spacer(modifier = Modifier.height(10.dp))
                HorizontalDivider(color = Slate200)
                Spacer(modifier = Modifier.height(10.dp))

                LazyColumn(modifier = Modifier.weight(1f)) {
                    item {
                        Text("DOCUMENTS (${documents.size})", fontWeight = FontWeight.Bold, fontSize = 11.sp, color = WhatsAppDarkTeal)
                        Spacer(modifier = Modifier.height(6.dp))
                    }

                    if (documents.isEmpty()) {
                        item {
                            Text("No documents shared in this group yet", fontSize = 11.sp, color = Slate400, modifier = Modifier.padding(vertical = 4.dp))
                        }
                    } else {
                        items(documents) { doc ->
                            DocumentAttachmentCard(
                                attachment = doc,
                                onClick = { onOpenDocument(doc) }
                            )
                            Spacer(modifier = Modifier.height(6.dp))
                        }
                    }

                    item {
                        Spacer(modifier = Modifier.height(14.dp))
                        Text("SITE PHOTOS & SPECIFICATIONS (${photos.size})", fontWeight = FontWeight.Bold, fontSize = 11.sp, color = WhatsAppDarkTeal)
                        Spacer(modifier = Modifier.height(6.dp))
                    }

                    if (photos.isEmpty()) {
                        item {
                            Text("No site photos shared in this group yet", fontSize = 11.sp, color = Slate400, modifier = Modifier.padding(vertical = 4.dp))
                        }
                    } else {
                        items(photos) { photo ->
                            ImageAttachmentCard(
                                attachment = photo,
                                onClick = { onOpenPhoto(photo) }
                            )
                            Spacer(modifier = Modifier.height(6.dp))
                        }
                    }
                }

                Spacer(modifier = Modifier.height(12.dp))

                Button(
                    onClick = onDismiss,
                    modifier = Modifier.align(Alignment.End),
                    colors = ButtonDefaults.buttonColors(containerColor = WhatsAppDarkTeal)
                ) {
                    Text("Close")
                }
            }
        }
    }
}

@Composable
fun GroupMembersDialog(
    group: ChatGroup,
    onDismiss: () -> Unit
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
                        Text(group.name, fontWeight = FontWeight.Bold, fontSize = 14.sp, color = Slate900)
                        Text("${group.members.size} Organization Members", fontSize = 11.sp, color = Slate500)
                    }
                    IconButton(onClick = onDismiss) {
                        Icon(Icons.Default.Close, contentDescription = "Close", tint = Slate400)
                    }
                }

                Spacer(modifier = Modifier.height(12.dp))
                HorizontalDivider(color = Slate200)
                Spacer(modifier = Modifier.height(12.dp))

                Surface(
                    color = Color(0xFFFEF3C7),
                    shape = RoundedCornerShape(8.dp),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Row(
                        modifier = Modifier.padding(8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(Icons.Default.Lock, contentDescription = null, tint = Color(0xFFD97706), modifier = Modifier.size(14.dp))
                        Spacer(modifier = Modifier.width(6.dp))
                        Text(group.confidentialityNotice, fontSize = 10.sp, color = Color(0xFF92400E))
                    }
                }

                Spacer(modifier = Modifier.height(12.dp))

                LazyColumn(modifier = Modifier.heightIn(max = 280.dp)) {
                    items(group.members) { member ->
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(vertical = 6.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Box(
                                modifier = Modifier
                                    .size(36.dp)
                                    .clip(CircleShape)
                                    .background(Color(0xFFE2E8F0)),
                                contentAlignment = Alignment.Center
                            ) {
                                Text(member.name.take(2).uppercase(), fontWeight = FontWeight.Bold, fontSize = 12.sp, color = Slate700)
                            }
                            Spacer(modifier = Modifier.width(10.dp))
                            Column(modifier = Modifier.weight(1f)) {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Text(member.name, fontWeight = FontWeight.SemiBold, fontSize = 12.sp, color = Slate900)
                                    if (member.isAdmin) {
                                        Spacer(modifier = Modifier.width(4.dp))
                                        Surface(color = Color(0xFFDCFCE7), shape = RoundedCornerShape(4.dp)) {
                                            Text("Group Admin", color = Color(0xFF15803D), fontSize = 8.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(horizontal = 4.dp, vertical = 1.dp))
                                        }
                                    }
                                }
                                Text("${member.role} • ${member.phone}", fontSize = 10.sp, color = Slate500)
                            }
                        }
                    }
                }

                Spacer(modifier = Modifier.height(14.dp))

                Button(
                    onClick = onDismiss,
                    modifier = Modifier.align(Alignment.End),
                    colors = ButtonDefaults.buttonColors(containerColor = WhatsAppDarkTeal)
                ) {
                    Text("Close")
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CreateChatGroupDialog(
    projects: List<Project>,
    onDismiss: () -> Unit,
    onCreate: (ChatGroup, String?) -> Unit
) {
    var groupName by remember { mutableStateOf("") }
    var groupDescription by remember { mutableStateOf("") }
    var selectedProjectId by remember { mutableStateOf<String?>("PRJ-01") }
    var selectedDivision by remember { mutableStateOf(Division.FURNITURE) }
    var isConfidential by remember { mutableStateOf(true) }
    var initialMessage by remember { mutableStateOf("Welcome team. Please use this confidential channel for site drawings, BoQs, and daily installation updates.") }

    var expandedProjectDropdown by remember { mutableStateOf(false) }

    val selectedProject = remember(selectedProjectId, projects) {
        projects.firstOrNull { it.id == selectedProjectId }
    }

    Dialog(onDismissRequest = onDismiss) {
        Card(
            shape = RoundedCornerShape(20.dp),
            colors = CardDefaults.cardColors(containerColor = Color.White),
            modifier = Modifier
                .fillMaxWidth()
                .fillMaxHeight(0.9f)
        ) {
            Column(modifier = Modifier.padding(20.dp)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column {
                        Text("Create Project Chat Group", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium, color = Slate900)
                        Text("WhatsApp-style confidential organization room", fontSize = 11.sp, color = Slate500)
                    }
                    IconButton(onClick = onDismiss) {
                        Icon(Icons.Default.Close, contentDescription = "Close", tint = Slate400)
                    }
                }

                Spacer(modifier = Modifier.height(10.dp))
                HorizontalDivider(color = Slate200)
                Spacer(modifier = Modifier.height(10.dp))

                LazyColumn(
                    modifier = Modifier.weight(1f),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    item {
                        OutlinedTextField(
                            value = groupName,
                            onValueChange = { groupName = it },
                            label = { Text("Group Name *") },
                            placeholder = { Text("e.g. Nanakramguda Villa - Execution & Snags") },
                            singleLine = true,
                            modifier = Modifier
                                .fillMaxWidth()
                                .testTag("create_group_name_input")
                        )
                    }

                    item {
                        // Project Link Selection Dropdown
                        Text("Link to Execution Project:", fontSize = 12.sp, fontWeight = FontWeight.Bold, color = Slate800)
                        Spacer(modifier = Modifier.height(4.dp))
                        Box(modifier = Modifier.fillMaxWidth()) {
                            OutlinedButton(
                                onClick = { expandedProjectDropdown = true },
                                modifier = Modifier.fillMaxWidth(),
                                shape = RoundedCornerShape(8.dp)
                            ) {
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.SpaceBetween,
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Text(
                                        text = if (selectedProject != null) "${selectedProject.projectNo} - ${selectedProject.customerName}" else "None (General Dept Chat)",
                                        fontSize = 12.sp,
                                        color = Slate900,
                                        maxLines = 1,
                                        overflow = TextOverflow.Ellipsis
                                    )
                                    Icon(Icons.Default.ArrowDropDown, contentDescription = null)
                                }
                            }

                            DropdownMenu(
                                expanded = expandedProjectDropdown,
                                onDismissRequest = { expandedProjectDropdown = false }
                            ) {
                                DropdownMenuItem(
                                    text = { Text("None (Departmental / General)") },
                                    onClick = {
                                        selectedProjectId = null
                                        expandedProjectDropdown = false
                                    }
                                )
                                projects.forEach { proj ->
                                    DropdownMenuItem(
                                        text = { Text("${proj.projectNo} - ${proj.customerName} (${proj.stage})") },
                                        onClick = {
                                            selectedProjectId = proj.id
                                            if (groupName.isBlank()) {
                                                groupName = "${proj.customerName} - Project Chat"
                                            }
                                            selectedDivision = proj.division
                                            expandedProjectDropdown = false
                                        }
                                    )
                                }
                            }
                        }
                    }

                    item {
                        OutlinedTextField(
                            value = groupDescription,
                            onValueChange = { groupDescription = it },
                            label = { Text("Group Purpose / Description") },
                            placeholder = { Text("Site drawings, daily installation updates, BoQ approvals") },
                            maxLines = 2,
                            modifier = Modifier.fillMaxWidth()
                        )
                    }

                    item {
                        // Confidential Toggle
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .clip(RoundedCornerShape(8.dp))
                                .background(if (isConfidential) Color(0xFFFEF3C7) else Color(0xFFF1F5F9))
                                .padding(10.dp),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Row(
                                modifier = Modifier.weight(1f),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Icon(Icons.Default.Lock, contentDescription = null, tint = if (isConfidential) Color(0xFFD97706) else Slate400, modifier = Modifier.size(20.dp))
                                Spacer(modifier = Modifier.width(8.dp))
                                Column {
                                    Text("Confidential Internal Discussion", fontSize = 12.sp, fontWeight = FontWeight.Bold, color = if (isConfidential) Color(0xFF92400E) else Slate800)
                                    Text("Restricted to MADIO personnel", fontSize = 10.sp, color = if (isConfidential) Color(0xFFB45309) else Slate500)
                                }
                            }
                            Switch(
                                checked = isConfidential,
                                onCheckedChange = { isConfidential = it }
                            )
                        }
                    }

                    item {
                        OutlinedTextField(
                            value = initialMessage,
                            onValueChange = { initialMessage = it },
                            label = { Text("Initial Welcome & Directive Message") },
                            maxLines = 3,
                            modifier = Modifier.fillMaxWidth()
                        )
                    }
                }

                Spacer(modifier = Modifier.height(14.dp))

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
                            val finalName = if (groupName.isNotBlank()) groupName else (selectedProject?.customerName ?: "New") + " Project Chat"
                            val newGroup = ChatGroup(
                                id = "GRP-" + System.currentTimeMillis().toString().takeLast(5),
                                name = finalName,
                                description = groupDescription,
                                projectId = selectedProject?.id,
                                projectNo = selectedProject?.projectNo,
                                projectName = selectedProject?.let { "${it.customerName} (${it.projectNo})" },
                                division = selectedDivision,
                                isConfidential = isConfidential,
                                confidentialityNotice = "Strictly internal MADIO Organization. Drawings, pricing, and site discussions are confidential.",
                                members = listOf(
                                    ChatMember("M1", "Madio Admin (You)", "Operations & MD", "+91 98480 00001", isAdmin = true),
                                    ChatMember("M2", selectedProject?.assignedEngineer ?: "Site Engineer", "Assigned Lead", "+91 98480 11223"),
                                    ChatMember("M3", "Sneha Rao", "Principal Architect", "+91 98480 33445"),
                                    ChatMember("M4", "Veerendra", "Installation Lead", "+91 98480 55667")
                                ),
                                lastMessage = initialMessage,
                                lastMessageTime = "Just now",
                                unreadCount = 0,
                                groupAvatarType = if (selectedProject != null) "PROJECT" else "MANAGEMENT"
                            )
                            onCreate(newGroup, initialMessage)
                        },
                        colors = ButtonDefaults.buttonColors(containerColor = WhatsAppDarkTeal),
                        modifier = Modifier.testTag("create_group_submit_btn")
                    ) {
                        Icon(Icons.Default.Check, contentDescription = null, modifier = Modifier.size(16.dp))
                        Spacer(modifier = Modifier.width(4.dp))
                        Text("Create WhatsApp Group")
                    }
                }
            }
        }
    }
}

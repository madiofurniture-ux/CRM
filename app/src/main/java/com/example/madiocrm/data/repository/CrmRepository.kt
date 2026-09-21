package com.example.madiocrm.data.repository

import com.example.madiocrm.data.model.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.util.UUID

class CrmRepository private constructor() {

    companion object {
        @Volatile
        private var instance: CrmRepository? = null

        fun getInstance(): CrmRepository {
            return instance ?: synchronized(this) {
                instance ?: CrmRepository().also { instance = it }
            }
        }
    }

    private val _leads = MutableStateFlow<List<Lead>>(emptyList())
    val leads: StateFlow<List<Lead>> = _leads.asStateFlow()

    private val _quotes = MutableStateFlow<List<Quote>>(emptyList())
    val quotes: StateFlow<List<Quote>> = _quotes.asStateFlow()

    private val _sales = MutableStateFlow<List<SaleOrder>>(emptyList())
    val sales: StateFlow<List<SaleOrder>> = _sales.asStateFlow()

    private val _projects = MutableStateFlow<List<Project>>(emptyList())
    val projects: StateFlow<List<Project>> = _projects.asStateFlow()

    private val _inventory = MutableStateFlow<List<InventoryItem>>(emptyList())
    val inventory: StateFlow<List<InventoryItem>> = _inventory.asStateFlow()

    private val _invoices = MutableStateFlow<List<TaxInvoice>>(emptyList())
    val invoices: StateFlow<List<TaxInvoice>> = _invoices.asStateFlow()

    private val _pettyCash = MutableStateFlow<List<PettyCashEntry>>(emptyList())
    val pettyCash: StateFlow<List<PettyCashEntry>> = _pettyCash.asStateFlow()

    private val _customers = MutableStateFlow<List<Customer>>(emptyList())
    val customers: StateFlow<List<Customer>> = _customers.asStateFlow()

    private val _architects = MutableStateFlow<List<Architect>>(emptyList())
    val architects: StateFlow<List<Architect>> = _architects.asStateFlow()

    private val _tasks = MutableStateFlow<List<TaskItem>>(emptyList())
    val tasks: StateFlow<List<TaskItem>> = _tasks.asStateFlow()

    // New Linked Pipeline StateFlows
    private val _visitors = MutableStateFlow<List<Visitor>>(emptyList())
    val visitors: StateFlow<List<Visitor>> = _visitors.asStateFlow()

    private val _surveys = MutableStateFlow<List<SiteSurvey>>(emptyList())
    val surveys: StateFlow<List<SiteSurvey>> = _surveys.asStateFlow()

    private val _projectWallets = MutableStateFlow<List<ProjectWallet>>(emptyList())
    val projectWallets: StateFlow<List<ProjectWallet>> = _projectWallets.asStateFlow()

    private val _projectExpenses = MutableStateFlow<List<ProjectExpense>>(emptyList())
    val projectExpenses: StateFlow<List<ProjectExpense>> = _projectExpenses.asStateFlow()

    private val _attendance = MutableStateFlow<List<AttendanceRecord>>(emptyList())
    val attendance: StateFlow<List<AttendanceRecord>> = _attendance.asStateFlow()

    // WhatsApp-Style Project & Internal Discussion Chat Groups
    private val _chatGroups = MutableStateFlow<List<ChatGroup>>(emptyList())
    val chatGroups: StateFlow<List<ChatGroup>> = _chatGroups.asStateFlow()

    private val _chatMessages = MutableStateFlow<Map<String, List<ChatMessage>>>(emptyMap())
    val chatMessages: StateFlow<Map<String, List<ChatMessage>>> = _chatMessages.asStateFlow()

    // Privacy Masking toggle for cost price / margins (as requested in MADIO CRM requirements)
    private val _isCostMasked = MutableStateFlow(true)
    val isCostMasked: StateFlow<Boolean> = _isCostMasked.asStateFlow()

    init {
        seedInitialData()
    }

    fun toggleCostMask() {
        _isCostMasked.value = !_isCostMasked.value
    }

    // Chat Group & Message Operations
    fun getMessagesForGroup(groupId: String): List<ChatMessage> {
        return _chatMessages.value[groupId] ?: emptyList()
    }

    fun sendChatMessage(
        groupId: String,
        text: String,
        attachment: ChatAttachment? = null,
        isConfidential: Boolean = false,
        senderName: String = "Madio Admin (You)",
        senderRole: String = "Operations & MD"
    ) {
        val message = ChatMessage(
            id = UUID.randomUUID().toString(),
            groupId = groupId,
            senderName = senderName,
            senderRole = senderRole,
            isFromMe = true,
            text = text,
            timestamp = "Just now",
            attachment = attachment,
            isConfidential = isConfidential,
            status = MessageStatus.READ
        )

        val currentList = _chatMessages.value[groupId] ?: emptyList()
        val updatedMap = _chatMessages.value.toMutableMap()
        updatedMap[groupId] = currentList + message
        _chatMessages.value = updatedMap

        val snippet = when {
            attachment != null && attachment.type == ChatAttachmentType.IMAGE -> "📷 Photo: ${if (attachment.title.isNotBlank()) attachment.title else text.ifBlank { "Site snapshot" }}"
            attachment != null && attachment.type == ChatAttachmentType.DOCUMENT -> "📄 Doc: ${attachment.title}"
            attachment != null && attachment.type == ChatAttachmentType.VOICE -> "🎤 Voice Note"
            else -> text
        }

        _chatGroups.value = _chatGroups.value.map { g ->
            if (g.id == groupId) {
                g.copy(
                    lastMessage = snippet,
                    lastMessageTime = "Just now",
                    unreadCount = 0
                )
            } else g
        }
    }

    fun createChatGroup(group: ChatGroup, initialMessage: String? = null): ChatGroup {
        val groupWithId = if (group.id.isBlank()) group.copy(id = "GRP-" + System.currentTimeMillis().toString().takeLast(5)) else group
        _chatGroups.value = listOf(groupWithId) + _chatGroups.value

        val initMsgList = mutableListOf<ChatMessage>()
        initMsgList.add(
            ChatMessage(
                id = UUID.randomUUID().toString(),
                groupId = groupWithId.id,
                senderName = "MADIO System",
                senderRole = "Bot",
                isFromMe = false,
                text = "🔒 Confidential internal discussion group created." + if (groupWithId.projectName != null) " Linked to project: ${groupWithId.projectName} (${groupWithId.projectNo ?: ""})" else "",
                timestamp = "Today",
                isSystemNotice = true
            )
        )
        if (!initialMessage.isNullOrBlank()) {
            initMsgList.add(
                ChatMessage(
                    id = UUID.randomUUID().toString(),
                    groupId = groupWithId.id,
                    senderName = "Madio Admin (You)",
                    senderRole = "Operations & MD",
                    isFromMe = true,
                    text = initialMessage,
                    timestamp = "Today",
                    isConfidential = groupWithId.isConfidential
                )
            )
        }
        val currentMap = _chatMessages.value.toMutableMap()
        currentMap[groupWithId.id] = initMsgList
        _chatMessages.value = currentMap

        return groupWithId
    }

    fun markGroupAsRead(groupId: String) {
        _chatGroups.value = _chatGroups.value.map { g ->
            if (g.id == groupId) g.copy(unreadCount = 0) else g
        }
    }

    fun getOrCreateGroupForProject(project: Project): ChatGroup {
        val existing = _chatGroups.value.firstOrNull { it.projectId == project.id || it.projectNo == project.projectNo }
        if (existing != null) return existing

        val newGroup = ChatGroup(
            id = "GRP-" + project.projectNo.replace("PRJ-", ""),
            name = "${project.customerName} - Site & Fitout",
            description = "Confidential project execution discussions, shop drawings, site snagging, and client approvals.",
            projectId = project.id,
            projectNo = project.projectNo,
            projectName = "${project.customerName} (${project.projectNo})",
            division = project.division,
            isConfidential = true,
            confidentialityNotice = "Strictly internal MADIO Organization. Drawings, pricing, and site discussions are confidential.",
            members = listOf(
                ChatMember("M1", "Madio Admin (You)", "Operations & MD", "+91 98480 00001", isAdmin = true),
                ChatMember("M2", project.assignedEngineer, "Assigned Site Engineer", "+91 98480 11223"),
                ChatMember("M3", "Sneha Rao", "Principal Architect", "+91 98480 33445"),
                ChatMember("M4", "Veerendra", "Installation Lead", "+91 98480 55667")
            ),
            lastMessage = "Group created for Project ${project.projectNo}",
            lastMessageTime = "Today",
            unreadCount = 0,
            groupAvatarType = "PROJECT"
        )
        return createChatGroup(newGroup)
    }

    // Visitor Operations
    fun addVisitor(visitor: Visitor) {
        _visitors.value = listOf(visitor) + _visitors.value
    }

    fun convertVisitorToLead(visitor: Visitor): Lead {
        val newLead = Lead(
            id = "LD-" + System.currentTimeMillis().toString().takeLast(4),
            name = visitor.name,
            phone = visitor.phone,
            source = "Walk-in Visitor",
            reference = visitor.purpose,
            division = visitor.division,
            stage = LeadStage.NEW,
            followUpDate = "Tomorrow",
            remarks = "Walk-in Inquiry: ${visitor.interestedIn}. Notes: ${visitor.notes}",
            estimatedValue = when (visitor.division) {
                Division.FURNITURE -> 280000.0
                Division.MAP -> 450000.0
                Division.DW -> 320000.0
                Division.ALL -> 250000.0
            },
            confidenceLevel = 75,
            assignedTo = visitor.attendedBy,
            createdAt = "Today",
            visitorId = visitor.id
        )
        _visitors.value = _visitors.value.map {
            if (it.id == visitor.id) it.copy(status = "Converted to Lead", convertedLeadId = newLead.id) else it
        }
        _leads.value = listOf(newLead) + _leads.value
        return newLead
    }

    // Survey Operations
    fun addSurvey(survey: SiteSurvey) {
        _surveys.value = listOf(survey) + _surveys.value
    }

    fun updateSurveyStatus(surveyId: String, status: String) {
        _surveys.value = _surveys.value.map {
            if (it.id == surveyId) it.copy(status = status) else it
        }
    }

    fun convertSurveyToQuote(survey: SiteSurvey): Quote {
        val lineItems = when (survey.division) {
            Division.MAP -> listOf(
                QuoteLineItem(
                    id = "L1",
                    description = "MAP Architectural Travertino Plaster (Surveyed: ${survey.wallAreaSqft.toInt()} sqft)",
                    sku = "MAP-ST-01",
                    qty = if (survey.wallAreaSqft > 0) survey.wallAreaSqft else 2500.0,
                    unit = "sqft",
                    rate = 145.0,
                    discountPct = 5.0,
                    taxPct = 18.0
                ),
                QuoteLineItem(
                    id = "L2",
                    description = "Moisture Seal Penetrating Primer (${survey.moistureLevel})",
                    sku = "MAP-PR-02",
                    qty = if (survey.wallAreaSqft > 0) survey.wallAreaSqft else 2500.0,
                    unit = "sqft",
                    rate = 28.0,
                    discountPct = 0.0,
                    taxPct = 18.0
                )
            )
            Division.DW -> listOf(
                QuoteLineItem(
                    id = "L1",
                    description = "Acoustic Double Glazed Casement Windows (${survey.apertureCount} apertures)",
                    sku = "DW-UPVC-60",
                    qty = survey.apertureCount.coerceAtLeast(2).toDouble(),
                    unit = "sets",
                    rate = 26000.0,
                    discountPct = 5.0,
                    taxPct = 18.0
                ),
                QuoteLineItem(
                    id = "L2",
                    description = "Thermal Break Heavy Duty Glazing Hardware & Installation",
                    sku = "DW-HDW-01",
                    qty = survey.apertureCount.coerceAtLeast(2).toDouble(),
                    unit = "sets",
                    rate = 6500.0,
                    discountPct = 0.0,
                    taxPct = 18.0
                )
            )
            else -> listOf(
                QuoteLineItem(
                    id = "L1",
                    description = "Survey-specified Custom Dining & Living Ensemble",
                    sku = "MF-CUST-01",
                    qty = 1.0,
                    unit = "lot",
                    rate = 195000.0,
                    discountPct = 8.0,
                    taxPct = 18.0
                )
            )
        }

        val newQuote = Quote(
            id = "QT-" + System.currentTimeMillis().toString().takeLast(4),
            quoteNo = "MAD-QT-" + (1000 + _quotes.value.size),
            date = "2026-09-20",
            customerName = survey.clientName,
            phone = survey.phone,
            division = survey.division,
            stage = DealStage.DESIGN_QUOTE,
            lineItems = lineItems,
            remarks = "Generated from Site Survey ${survey.surveyNo}. Notes: ${survey.notes}"
        )

        _surveys.value = _surveys.value.map {
            if (it.id == survey.id) it.copy(status = "Quote Generated", linkedQuoteId = newQuote.id) else it
        }
        _quotes.value = listOf(newQuote) + _quotes.value
        return newQuote
    }

    // Lead Operations
    fun addLead(lead: Lead) {
        _leads.value = listOf(lead) + _leads.value
    }

    fun updateLeadStage(leadId: String, newStage: LeadStage) {
        _leads.value = _leads.value.map {
            if (it.id == leadId) it.copy(stage = newStage) else it
        }
    }

    fun deleteLead(leadId: String) {
        _leads.value = _leads.value.filterNot { it.id == leadId }
    }

    // Quote Operations
    fun addQuote(quote: Quote) {
        _quotes.value = listOf(quote) + _quotes.value
    }

    fun updateQuoteStage(quoteId: String, newStage: DealStage) {
        _quotes.value = _quotes.value.map {
            if (it.id == quoteId) it.copy(stage = newStage) else it
        }
    }

    fun convertQuoteToSale(quote: Quote): SaleOrder {
        val newSale = SaleOrder(
            id = UUID.randomUUID().toString(),
            saleNo = "SO-" + System.currentTimeMillis().toString().takeLast(4),
            date = "2026-09-20",
            customerName = quote.customerName,
            division = quote.division,
            quoteRef = quote.quoteNo,
            totalValue = quote.grandTotal,
            paidAmount = quote.grandTotal * 0.4, // 40% initial booking advance
            deliveryDate = "2026-10-15",
            status = SaleStatus.PARTIAL,
            remarks = "Converted from Quote ${quote.quoteNo}"
        )
        _sales.value = listOf(newSale) + _sales.value
        updateQuoteStage(quote.id, DealStage.WON)

        // Automatically generate Tax Invoice for booking advance
        val newInvoice = TaxInvoice(
            id = "INV-" + System.currentTimeMillis().toString().takeLast(4),
            invoiceNo = "MAD-INV-2026-" + (100 + _invoices.value.size),
            date = "2026-09-20",
            customerName = quote.customerName,
            phone = quote.phone,
            subtotal = quote.subtotal * 0.4,
            gstRate = 18.0,
            totalAmount = quote.grandTotal * 0.4,
            paidAmount = quote.grandTotal * 0.4,
            status = "Paid"
        )
        _invoices.value = listOf(newInvoice) + _invoices.value

        // Automatically initiate Project execution and link petty cash wallet
        initiateProjectFromSale(newSale)

        return newSale
    }

    fun initiateProjectFromSale(sale: SaleOrder): Project {
        val projId = "PRJ-" + System.currentTimeMillis().toString().takeLast(4)
        val walletId = "WLT-" + System.currentTimeMillis().toString().takeLast(4)
        val initialWalletAllocation = (sale.totalValue * 0.05).coerceIn(15000.0, 50000.0)

        val newProject = Project(
            id = projId,
            projectNo = "PRJ-2609-" + (_projects.value.size + 1).toString().padStart(2, '0'),
            customerName = "${sale.customerName} Site",
            phone = "+91 98490 00000",
            division = sale.division,
            contractValue = sale.totalValue,
            paidAmount = sale.paidAmount,
            stage = "Site Survey",
            completionPct = 15,
            siteAddress = "Site Execution - ${sale.customerName}",
            assignedEngineer = when (sale.division) {
                Division.MAP -> "Kalyan Site PM"
                Division.DW -> "Phani Kumar"
                else -> "Veerendra"
            },
            targetDate = sale.deliveryDate.ifBlank { "2026-10-25" },
            milestones = listOf(
                Milestone("Site Survey & Measurements Sign-off", true, "Today"),
                Milestone("Material Dispatch & Warehouse QA", false),
                Milestone("On-Site Installation & Assembly", false),
                Milestone("Snagging & Client Quality Acceptance", false),
                Milestone("Final Handover & Warranty Certificate", false)
            ),
            dailyLogCount = 1,
            walletId = walletId
        )

        val newWallet = ProjectWallet(
            id = walletId,
            projectId = projId,
            projectNo = newProject.projectNo,
            projectName = newProject.customerName,
            clientName = sale.customerName,
            division = sale.division,
            totalAllocated = initialWalletAllocation,
            totalSpent = 0.0,
            engineerName = newProject.assignedEngineer
        )

        _projects.value = listOf(newProject) + _projects.value
        _projectWallets.value = listOf(newWallet) + _projectWallets.value
        return newProject
    }

    // Project Wallet & Petty Cash Operations
    fun allocateToProjectWallet(walletId: String, amount: Double) {
        _projectWallets.value = _projectWallets.value.map {
            if (it.id == walletId) it.copy(totalAllocated = it.totalAllocated + amount) else it
        }
    }

    fun addProjectExpense(expense: ProjectExpense) {
        _projectExpenses.value = listOf(expense) + _projectExpenses.value
        // Real-time deduction from project wallet
        _projectWallets.value = _projectWallets.value.map {
            if (it.id == expense.walletId) it.copy(totalSpent = it.totalSpent + expense.amount) else it
        }
        // Mirror in general Petty Cashbook
        val cashEntry = PettyCashEntry(
            id = expense.id,
            date = expense.date,
            type = "OUT",
            category = expense.category,
            amount = expense.amount,
            description = "[${expense.projectNo}] ${expense.description}",
            party = expense.paidTo,
            approved = expense.approved
        )
        _pettyCash.value = listOf(cashEntry) + _pettyCash.value
    }

    // Attendance Operations
    fun punchAttendance(record: AttendanceRecord) {
        _attendance.value = listOf(record) + _attendance.value
    }

    // Sale Operations
    fun addSale(sale: SaleOrder) {
        _sales.value = listOf(sale) + _sales.value
    }

    fun recordPayment(saleId: String, amount: Double) {
        _sales.value = _sales.value.map { sale ->
            if (sale.id == saleId) {
                val newPaid = sale.paidAmount + amount
                val newStatus = if (newPaid >= sale.totalValue) SaleStatus.PAID else SaleStatus.PARTIAL
                sale.copy(paidAmount = newPaid, status = newStatus)
            } else sale
        }
    }

    // Project Operations
    fun updateProjectMilestone(projectId: String, milestoneIndex: Int, completed: Boolean) {
        _projects.value = _projects.value.map { project ->
            if (project.id == projectId) {
                val updatedMilestones = project.milestones.mapIndexed { idx, m ->
                    if (idx == milestoneIndex) m.copy(completed = completed, completedAt = if (completed) "Today" else "") else m
                }
                val completedCount = updatedMilestones.count { it.completed }
                val pct = if (updatedMilestones.isNotEmpty()) (completedCount * 100) / updatedMilestones.size else 0
                val newStage = when {
                    pct == 100 -> "Completed"
                    pct >= 80 -> "Handover"
                    pct >= 50 -> "Execution"
                    else -> "Site Survey"
                }
                project.copy(milestones = updatedMilestones, completionPct = pct, stage = newStage)
            } else project
        }
    }

    // Inventory Operations
    fun updateInventoryQty(itemId: String, delta: Int) {
        _inventory.value = _inventory.value.map { item ->
            if (item.id == itemId) {
                val newQty = (item.qty + delta).coerceAtLeast(0)
                val newStatus = when {
                    newQty <= 0 -> "Out of Stock"
                    newQty <= 2 -> "Low Stock"
                    else -> "In Stock"
                }
                item.copy(qty = newQty, status = newStatus)
            } else item
        }
    }

    fun addInventoryItem(item: InventoryItem) {
        _inventory.value = listOf(item) + _inventory.value
    }

    // Petty Cash Operations
    fun addPettyCash(entry: PettyCashEntry) {
        _pettyCash.value = listOf(entry) + _pettyCash.value
    }

    // Task Operations
    fun toggleTask(taskId: String) {
        _tasks.value = _tasks.value.map {
            if (it.id == taskId) it.copy(isDone = !it.isDone) else it
        }
    }

    fun addTask(task: TaskItem) {
        _tasks.value = listOf(task) + _tasks.value
    }

    // Customer & Architect Operations
    fun addCustomer(customer: Customer) {
        _customers.value = listOf(customer) + _customers.value
    }

    fun addArchitect(architect: Architect) {
        _architects.value = listOf(architect) + _architects.value
    }

    private fun seedInitialData() {
        _leads.value = listOf(
            Lead(
                id = "LD-101",
                name = "Mr. Srinivas Rao",
                phone = "+91 98480 22331",
                source = "Architect Referral",
                reference = "Ar. Sirisha Studio",
                division = Division.FURNITURE,
                stage = LeadStage.QUOTED,
                followUpDate = "2026-09-22",
                remarks = "Villa dining setup and living room wall claddings. Quote shared.",
                estimatedValue = 385000.0,
                confidenceLevel = 85,
                assignedTo = "Ravi Teja",
                createdAt = "2026-09-18"
            ),
            Lead(
                id = "LD-102",
                name = "Dr. Avinash Reddy",
                phone = "+91 99890 44552",
                source = "Walk-in Showroom",
                reference = "Jubilee Hills Walk-in",
                division = Division.MAP,
                stage = LeadStage.CONTACTED,
                followUpDate = "2026-09-21",
                remarks = "Exterior acrylic plastering 4,500 sqft. Needs substrate moisture test.",
                estimatedValue = 620000.0,
                confidenceLevel = 75,
                assignedTo = "Kalyan",
                createdAt = "2026-09-19"
            ),
            Lead(
                id = "LD-103",
                name = "Smt. Geetha Varma",
                phone = "+91 97011 88990",
                source = "Instagram",
                reference = "@madiointeriors ad campaign",
                division = Division.DW,
                stage = LeadStage.NEW,
                followUpDate = "2026-09-20",
                remarks = "Slim-profile sliding doors & acoustic double-glazed windows.",
                estimatedValue = 540000.0,
                confidenceLevel = 60,
                assignedTo = "Phani Kumar",
                createdAt = "2026-09-20"
            ),
            Lead(
                id = "LD-104",
                name = "Controno Interiors",
                phone = "+91 98499 11223",
                source = "Architect",
                reference = "Direct Partner",
                division = Division.FURNITURE,
                stage = LeadStage.QUALIFIED,
                followUpDate = "2026-09-23",
                remarks = "Beds and lounge chairs bulk requirement for Penthouse project.",
                estimatedValue = 780000.0,
                confidenceLevel = 90,
                assignedTo = "Deepak Reddy",
                createdAt = "2026-09-15"
            ),
            Lead(
                id = "LD-105",
                name = "Tushar Agrawal",
                phone = "+91 94401 55667",
                source = "Website",
                reference = "Contact Form",
                division = Division.FURNITURE,
                stage = LeadStage.WON,
                followUpDate = "Closed",
                remarks = "Italian marble dining table & leather chairs booked.",
                estimatedValue = 305000.0,
                confidenceLevel = 100,
                assignedTo = "Ravi Teja",
                createdAt = "2026-09-10"
            )
        )

        _quotes.value = listOf(
            Quote(
                id = "QT-2026-01",
                quoteNo = "MAD-QT-0891",
                date = "2026-09-18",
                customerName = "Mr. Srinivas Rao",
                phone = "+91 98480 22331",
                division = Division.FURNITURE,
                stage = DealStage.DESIGN_QUOTE,
                lineItems = listOf(
                    QuoteLineItem("L1", "8024 Wood & Ice Flower Marble Dining Table", "MF-8024", 1.0, "set", 120000.0, 5.0, 18.0),
                    QuoteLineItem("L2", "Kelly Dining Chairs - Dark Brown Pure Leather", "MF-DC-01", 6.0, "pcs", 14500.0, 0.0, 18.0),
                    QuoteLineItem("L3", "Lake & Mountains Wall Accent 1500mm", "MF-W05", 1.0, "pcs", 28000.0, 0.0, 18.0)
                ),
                remarks = "Includes white-glove site delivery and installation."
            ),
            Quote(
                id = "QT-2026-02",
                quoteNo = "MAD-QT-0892",
                date = "2026-09-19",
                customerName = "Dr. Avinash Reddy",
                phone = "+91 99890 44552",
                division = Division.MAP,
                stage = DealStage.SITE_VISIT,
                lineItems = listOf(
                    QuoteLineItem("L1", "MAP Stucco Travertino Base & Topcoat", "MAP-ST-01", 3500.0, "sqft", 140.0, 5.0, 18.0),
                    QuoteLineItem("L2", "Surface Prep & Anti-Efflorescence Primer", "MAP-PR-02", 3500.0, "sqft", 25.0, 0.0, 18.0)
                ),
                remarks = "5-year exterior weather warranty included."
            ),
            Quote(
                id = "QT-2026-03",
                quoteNo = "MAD-QT-0893",
                date = "2026-09-16",
                customerName = "Controno Interiors",
                phone = "+91 98499 11223",
                division = Division.FURNITURE,
                stage = DealStage.NEGOTIATION,
                lineItems = listOf(
                    QuoteLineItem("L1", "Hangchen Upholstered King Size Bed", "MF-BED-15", 2.0, "sets", 85000.0, 8.0, 18.0),
                    QuoteLineItem("L2", "Xinghao Pure Leather Lounge Chair", "MF-LC-13", 2.0, "pcs", 45000.0, 5.0, 18.0)
                ),
                remarks = "Architect discount applied. Awaiting final PO."
            )
        )

        _sales.value = listOf(
            SaleOrder(
                id = "SO-501",
                saleNo = "SO-2609-001",
                date = "2026-09-14",
                customerName = "Sonu Goud",
                division = Division.FURNITURE,
                quoteRef = "MAD-QT-0870",
                totalValue = 245000.0,
                paidAmount = 180000.0,
                deliveryDate = "2026-09-28",
                status = SaleStatus.PARTIAL,
                remarks = "2307 Double Foot Lauren Black Wood + Marble Table"
            ),
            SaleOrder(
                id = "SO-502",
                saleNo = "SO-2609-002",
                date = "2026-09-10",
                customerName = "Tushar Agrawal",
                division = Division.FURNITURE,
                quoteRef = "MAD-QT-0865",
                totalValue = 305000.0,
                paidAmount = 305000.0,
                deliveryDate = "2026-09-22",
                status = SaleStatus.PAID,
                remarks = "Full settlement cleared. Dispatched from warehouse."
            ),
            SaleOrder(
                id = "SO-503",
                saleNo = "SO-2609-003",
                date = "2026-09-17",
                customerName = "Shankar Reddy",
                division = Division.MAP,
                quoteRef = "MAD-QT-0882",
                totalValue = 480000.0,
                paidAmount = 200000.0,
                deliveryDate = "2026-10-05",
                status = SaleStatus.PARTIAL,
                remarks = "MAP Acrylic Plaster site supply phase 1."
            ),
            SaleOrder(
                id = "SO-504",
                saleNo = "SO-2609-004",
                date = "2026-09-19",
                customerName = "Kiran Sir",
                division = Division.DW,
                quoteRef = "MAD-QT-0888",
                totalValue = 185000.0,
                paidAmount = 50000.0,
                deliveryDate = "2026-10-12",
                status = SaleStatus.PENDING,
                remarks = "Advance cheque under clearance."
            )
        )

        _projects.value = listOf(
            Project(
                id = "PRJ-301",
                projectNo = "PRJ-2609-01",
                customerName = "Shankar Reddy Villa",
                phone = "+91 98490 77112",
                division = Division.MAP,
                contractValue = 480000.0,
                paidAmount = 200000.0,
                stage = "Execution",
                completionPct = 65,
                siteAddress = "Plot 42, Financial District, Nanakramguda, Hyderabad",
                assignedEngineer = "Kalyan Site PM",
                targetDate = "2026-10-05",
                milestones = listOf(
                    Milestone("Substrate Moisture & PH Test", true, "2026-09-12"),
                    Milestone("Surface Prep & Anti-Crack Mesh", true, "2026-09-16"),
                    Milestone("Undercoat Acrylic Primer", true, "2026-09-19"),
                    Milestone("Topcoat Architectural Texture", false),
                    Milestone("Final Protective Sealer & Handover", false)
                ),
                dailyLogCount = 7
            ),
            Project(
                id = "PRJ-302",
                projectNo = "PRJ-2609-02",
                customerName = "Sonu Goud Residence",
                phone = "+91 98492 33445",
                division = Division.FURNITURE,
                contractValue = 245000.0,
                paidAmount = 180000.0,
                stage = "Snagging",
                completionPct = 85,
                siteAddress = "Flat 1402, My Home Bhooja, Hitec City",
                assignedEngineer = "Veerendra",
                targetDate = "2026-09-28",
                milestones = listOf(
                    Milestone("Site Dimensions Verification", true, "2026-09-15"),
                    Milestone("Warehouse Quality Check", true, "2026-09-17"),
                    Milestone("Delivery & Assembly", true, "2026-09-19"),
                    Milestone("Snagging & Polishing", false),
                    Milestone("Client Sign-off", false)
                ),
                dailyLogCount = 4
            ),
            Project(
                id = "PRJ-303",
                projectNo = "PRJ-2609-03",
                customerName = "Srinivas Botanica Villa",
                phone = "+91 98491 55667",
                division = Division.DW,
                contractValue = 360000.0,
                paidAmount = 150000.0,
                stage = "Site Survey",
                completionPct = 25,
                siteAddress = "Botanica Villas, Gachibowli, Hyderabad",
                assignedEngineer = "Phani Kumar",
                targetDate = "2026-10-20",
                milestones = listOf(
                    Milestone("Laser Site Aperture Survey", true, "2026-09-18"),
                    Milestone("Lintel & Glass Specs Review", false),
                    Milestone("Factory Frame Fabrication", false),
                    Milestone("On-site Glazing Installation", false),
                    Milestone("Acoustic Testing & Handover", false)
                ),
                dailyLogCount = 2
            )
        )

        _inventory.value = listOf(
            InventoryItem(
                id = "INV-001",
                sku = "MF-001",
                name = "Ficus Microcarpa Decorative Tree",
                category = "Artificial Plants",
                vendor = "ZHI RAN SHE",
                qty = 4,
                costPrice = 32000.0,
                mrp = 98000.0,
                marginPct = 67.3,
                status = "In Stock",
                location = "Showroom Floor 1",
                division = Division.FURNITURE
            ),
            InventoryItem(
                id = "INV-002",
                sku = "MF-8024",
                name = "8024 Marble Dining Table Wood + Ice Flower",
                category = "Dining Tables",
                vendor = "TENG YUF FURNITURE",
                qty = 2,
                costPrice = 44000.0,
                mrp = 132000.0,
                marginPct = 66.7,
                status = "In Stock",
                location = "Showroom Floor 2",
                division = Division.FURNITURE
            ),
            InventoryItem(
                id = "INV-003",
                sku = "MF-DC-11",
                name = "Kelly Dining Chair - Dark Brown Leather",
                category = "Chairs",
                vendor = "KELLY FURNISHINGS",
                qty = 18,
                costPrice = 5600.0,
                mrp = 17000.0,
                marginPct = 67.0,
                status = "In Stock",
                location = "Warehouse Rack B",
                division = Division.FURNITURE
            ),
            InventoryItem(
                id = "INV-004",
                sku = "MF-LC-13",
                name = "Xinghao Lounge Chair - Cat Claw Fabric & Leather",
                category = "Lounge Chairs",
                vendor = "XINGHAO LOUNGE CHAIR",
                qty = 3,
                costPrice = 18000.0,
                mrp = 54600.0,
                marginPct = 67.0,
                status = "In Stock",
                location = "Showroom Floor 1",
                division = Division.FURNITURE
            ),
            InventoryItem(
                id = "INV-005",
                sku = "MF-SF-19",
                name = "Vernessy Luxury L-Shape Modular Sofa",
                category = "Sofas",
                vendor = "VERNESSY FURNITURE",
                qty = 1,
                costPrice = 115600.0,
                mrp = 352300.0,
                marginPct = 67.2,
                status = "Low Stock",
                location = "Showroom Floor 1",
                division = Division.FURNITURE
            ),
            InventoryItem(
                id = "INV-006",
                sku = "MAP-ST-10",
                name = "MAP Travertino Plaster 25kg Drum",
                category = "Wall Plaster",
                vendor = "MAP ITALIA / XIN XIN",
                qty = 45,
                costPrice = 2800.0,
                mrp = 7500.0,
                marginPct = 62.6,
                status = "In Stock",
                location = "Warehouse Central",
                division = Division.MAP
            ),
            InventoryItem(
                id = "INV-007",
                sku = "DW-UPVC-60",
                name = "Acoustic Double Glazed Casement 1200x1500",
                category = "UPVC Windows",
                vendor = "MADIO FABRICATION",
                qty = 6,
                costPrice = 8500.0,
                mrp = 22000.0,
                marginPct = 61.4,
                status = "In Stock",
                location = "D&W Assembly Bay",
                division = Division.DW
            )
        )

        _invoices.value = listOf(
            TaxInvoice(
                id = "INV-901",
                invoiceNo = "MAD-INV-2026-081",
                date = "2026-09-12",
                customerName = "Tushar Agrawal",
                phone = "+91 94401 55667",
                subtotal = 258474.0,
                gstRate = 18.0,
                totalAmount = 305000.0,
                paidAmount = 305000.0,
                status = "Paid"
            ),
            TaxInvoice(
                id = "INV-902",
                invoiceNo = "MAD-INV-2026-082",
                date = "2026-09-15",
                customerName = "Sonu Goud",
                phone = "+91 98492 33445",
                subtotal = 207627.0,
                gstRate = 18.0,
                totalAmount = 245000.0,
                paidAmount = 180000.0,
                status = "Partially Paid"
            )
        )

        _pettyCash.value = listOf(
            PettyCashEntry("PC-01", "2026-09-20", "OUT", "Refreshments", 650.0, "Client hospitality & meeting beverages", "Chai Point", true),
            PettyCashEntry("PC-02", "2026-09-19", "OUT", "Hardware", 2400.0, "Screws & anchors for My Home Bhooja installation", "Sri Balaji Hardware", true),
            PettyCashEntry("PC-03", "2026-09-18", "OUT", "Fuel", 1500.0, "Site survey diesel allowance - Kalyan", "HPCL Petrol", true),
            PettyCashEntry("PC-04", "2026-09-17", "IN", "Advance", 25000.0, "Showroom cash box replenishment by Finance", "Director Cash Transfer", true)
        )

        _customers.value = listOf(
            Customer("CST-01", "Mr. Srinivas Rao", "+91 98480 22331", "srinivas.r@gmail.com", "Rainbow Vistas, Hitec City", Division.FURNITURE, "Active", 385000.0, 2),
            Customer("CST-02", "Dr. Avinash Reddy", "+91 99890 44552", "dr.avinash@hospital.org", "Road 36, Jubilee Hills", Division.MAP, "Active", 620000.0, 1),
            Customer("CST-03", "Tushar Agrawal", "+91 94401 55667", "tushar@techventures.io", "Boulder Hills Golf Villa", Division.FURNITURE, "Active", 305000.0, 1),
            Customer("CST-04", "Sonu Goud", "+91 98492 33445", "sonu.goud@construction.co", "My Home Bhooja Tower 2", Division.FURNITURE, "Active", 245000.0, 1)
        )

        _architects.value = listOf(
            Architect("ARC-01", "Ar. Sirisha K.", "Sirisha Design Associates", "+91 98490 00112", "Banjara Hills", 7.5, 8),
            Architect("ARC-02", "Ar. Deepak Reddy", "Reddy & Partners Architects", "+91 98490 00334", "Madhapur", 6.0, 5),
            Architect("ARC-03", "Controno Interiors", "Controno Design Studio", "+91 98499 11223", "Gachibowli", 8.0, 12)
        )

        _tasks.value = listOf(
            TaskItem("TK-01", "Follow up with Srinivas Rao regarding dining table quote discount", TaskPriority.HIGH, "2026-09-21", "Follow-up", false, "Mr. Srinivas Rao"),
            TaskItem("TK-02", "Arrange sample swatch tiles for Dr. Avinash MAP plaster site", TaskPriority.HIGH, "2026-09-21", "Site", false, "Dr. Avinash Reddy"),
            TaskItem("TK-03", "Conduct final snagging check for Sonu Goud My Home Bhooja", TaskPriority.URGENT, "2026-09-22", "Snagging", false, "Sonu Goud"),
            TaskItem("TK-04", "Schedule factory fabrication for Botanica UPVC survey DW-088", TaskPriority.MEDIUM, "2026-09-23", "Production", false, "Srinivas Botanica"),
            TaskItem("TK-05", "Audit showroom display tags & update MRP stickers", TaskPriority.LOW, "2026-09-25", "Store", true, "Showroom")
        )

        _visitors.value = listOf(
            Visitor(
                id = "VIS-101",
                visitorNo = "VST-0920-01",
                name = "Anand Kothari",
                phone = "+91 98480 11990",
                email = "anand.kothari@gmail.com",
                purpose = "Showroom Walk-in",
                division = Division.FURNITURE,
                interestedIn = "Italian marble dining table 8-seater & luxury accent chairs",
                attendedBy = "Sirisha Reception",
                checkInTime = "Today, 10:30 AM",
                status = "Inquiry Logged",
                notes = "Client building a luxury villa in Kokapet. Needs delivery before Diwali."
            ),
            Visitor(
                id = "VIS-102",
                visitorNo = "VST-0920-02",
                name = "Mrs. Lavanya Rao",
                phone = "+91 99891 22334",
                email = "lavanya.rao@outlook.com",
                purpose = "Material Selection",
                division = Division.MAP,
                interestedIn = "Exterior Travertino & Stucco antique plaster swatches",
                attendedBy = "Ravi Teja",
                checkInTime = "Today, 11:15 AM",
                status = "Inquiry Logged",
                notes = "Elevation plaster requirement ~5,000 sqft. Requested site moisture inspection."
            ),
            Visitor(
                id = "VIS-103",
                visitorNo = "VST-0920-03",
                name = "Ar. Rohit Varma",
                phone = "+91 97000 88776",
                email = "rohit@varma-arch.com",
                purpose = "Architect Consultation",
                division = Division.DW,
                interestedIn = "Acoustic slim-profile sliding doors & terrace glazing",
                attendedBy = "Phani Kumar",
                checkInTime = "Today, 11:45 AM",
                status = "Inquiry Logged",
                notes = "Discussed 4 duplex penthouses in Gachibowli. Brought architectural drawings."
            ),
            Visitor(
                id = "VIS-104",
                visitorNo = "VST-0919-01",
                name = "Mr. Srinivas Rao",
                phone = "+91 98480 22331",
                email = "srinivas.r@gmail.com",
                purpose = "Showroom Walk-in",
                division = Division.FURNITURE,
                interestedIn = "Dining setup & living claddings",
                attendedBy = "Ravi Teja",
                checkInTime = "Yesterday, 04:00 PM",
                status = "Converted to Lead",
                convertedLeadId = "LD-101",
                notes = "Converted to Lead LD-101. Quote MAD-QT-0891 submitted."
            )
        )

        _surveys.value = listOf(
            SiteSurvey(
                id = "SRV-01",
                surveyNo = "SRV-2609-01",
                leadId = "LD-102",
                clientName = "Dr. Avinash Reddy",
                phone = "+91 99890 44552",
                siteAddress = "Road 36, Jubilee Hills, Hyderabad",
                division = Division.MAP,
                surveyDate = "2026-09-19",
                engineerName = "Kalyan Site PM",
                measurements = "East facade: 1,800 sqft, West facade: 1,400 sqft, North balcony: 800 sqft. Total: 4,000 sqft",
                moistureLevel = "Substrate moisture: 9.8% (Ready for primer)",
                apertureCount = 0,
                wallAreaSqft = 4000.0,
                notes = "Cured plaster ready for Travertino coat. External scaffolding in place.",
                photoCount = 6,
                status = "Completed",
                linkedQuoteId = "QT-2026-02"
            ),
            SiteSurvey(
                id = "SRV-02",
                surveyNo = "SRV-2609-02",
                leadId = "LD-103",
                clientName = "Smt. Geetha Varma",
                phone = "+91 97011 88990",
                siteAddress = "Villa 28, Boulder Hills, Gachibowli",
                division = Division.DW,
                surveyDate = "2026-09-20",
                engineerName = "Phani Kumar",
                measurements = "Master Bedroom: 2400x2100mm, Living Slider: 3600x2400mm, 2x Bath Vents: 600x600mm",
                moistureLevel = "N/A",
                apertureCount = 4,
                wallAreaSqft = 0.0,
                notes = "Client requested high acoustic damping against nearby golf course noise.",
                photoCount = 4,
                status = "Scheduled",
                linkedQuoteId = null
            ),
            SiteSurvey(
                id = "SRV-03",
                surveyNo = "SRV-2609-03",
                leadId = "LD-101",
                clientName = "Mr. Srinivas Rao",
                phone = "+91 98480 22331",
                siteAddress = "Rainbow Vistas, Hitec City",
                division = Division.FURNITURE,
                surveyDate = "2026-09-17",
                engineerName = "Veerendra",
                measurements = "Dining Hall: 16x14 ft, Service elevator clearance: 8.5x4.5 ft (Elevator verified)",
                moistureLevel = "N/A",
                apertureCount = 0,
                wallAreaSqft = 0.0,
                notes = "Verified freight elevator handles 8-seater stone tabletop seamlessly.",
                photoCount = 3,
                status = "Completed",
                linkedQuoteId = "QT-2026-01"
            )
        )

        _projectWallets.value = listOf(
            ProjectWallet(
                id = "WLT-301",
                projectId = "PRJ-301",
                projectNo = "PRJ-2609-01",
                projectName = "Shankar Reddy Villa",
                clientName = "Shankar Reddy",
                division = Division.MAP,
                totalAllocated = 25000.0,
                totalSpent = 8400.0,
                engineerName = "Kalyan Site PM"
            ),
            ProjectWallet(
                id = "WLT-302",
                projectId = "PRJ-302",
                projectNo = "PRJ-2609-02",
                projectName = "Sonu Goud Residence",
                clientName = "Sonu Goud",
                division = Division.FURNITURE,
                totalAllocated = 15000.0,
                totalSpent = 4200.0,
                engineerName = "Veerendra"
            ),
            ProjectWallet(
                id = "WLT-303",
                projectId = "PRJ-303",
                projectNo = "PRJ-2609-03",
                projectName = "Srinivas Botanica Villa",
                clientName = "Srinivas Botanica",
                division = Division.DW,
                totalAllocated = 18000.0,
                totalSpent = 3100.0,
                engineerName = "Phani Kumar"
            )
        )

        _projectExpenses.value = listOf(
            ProjectExpense(
                id = "PCE-01",
                walletId = "WLT-301",
                projectId = "PRJ-301",
                projectNo = "PRJ-2609-01",
                date = "2026-09-18",
                amount = 4500.0,
                category = "Daily Labour Advance",
                description = "Scaffolding plasterers daily food & conveyance advance (3 staff)",
                paidTo = "Mahesh Mestri",
                approved = true
            ),
            ProjectExpense(
                id = "PCE-02",
                walletId = "WLT-301",
                projectId = "PRJ-301",
                projectNo = "PRJ-2609-01",
                date = "2026-09-19",
                amount = 2400.0,
                category = "Hardware/Fasteners",
                description = "Surface masking tapes, plastic sheets, and putty blades",
                paidTo = "Sri Balaji Hardware",
                approved = true
            ),
            ProjectExpense(
                id = "PCE-03",
                walletId = "WLT-301",
                projectId = "PRJ-301",
                projectNo = "PRJ-2609-01",
                date = "2026-09-20",
                amount = 1500.0,
                category = "Tempo Freight/Unloading",
                description = "Auto tempo hire for 12 Travertino drums unloading at site",
                paidTo = "Yadagiri Tempo",
                approved = true
            ),
            ProjectExpense(
                id = "PCE-04",
                walletId = "WLT-302",
                projectId = "PRJ-302",
                projectNo = "PRJ-2609-02",
                date = "2026-09-19",
                amount = 2800.0,
                category = "Hardware/Fasteners",
                description = "M10 heavy anchor bolts & floor felt glides for dining table",
                paidTo = "Hitec Hardware Hub",
                approved = true
            ),
            ProjectExpense(
                id = "PCE-05",
                walletId = "WLT-302",
                projectId = "PRJ-302",
                projectNo = "PRJ-2609-02",
                date = "2026-09-20",
                amount = 1400.0,
                category = "Site Refreshments",
                description = "Drinking water cans & refreshments during delivery team assembly",
                paidTo = "Cool Point Refreshments",
                approved = true
            ),
            ProjectExpense(
                id = "PCE-06",
                walletId = "WLT-303",
                projectId = "PRJ-303",
                projectNo = "PRJ-2609-03",
                date = "2026-09-18",
                amount = 3100.0,
                category = "Conveyance/Fuel",
                description = "Laser survey team site travel & instrument calibration allowance",
                paidTo = "Phani Kumar Survey",
                approved = true
            )
        )

        _attendance.value = listOf(
            AttendanceRecord(
                id = "ATT-01",
                staffName = "Kalyan Site PM",
                role = "Project Manager - MAP",
                timestamp = "Today, 09:15 AM",
                siteOrOffice = "Shankar Reddy Villa, Nanakramguda",
                latitude = 17.4185,
                longitude = 78.3496,
                photoBitmap = null,
                status = "On-Site Check-In",
                notes = "Supervising Travertino primer application"
            ),
            AttendanceRecord(
                id = "ATT-02",
                staffName = "Veerendra",
                role = "Installation Lead - Furniture",
                timestamp = "Today, 09:30 AM",
                siteOrOffice = "My Home Bhooja, Hitec City",
                latitude = 17.4399,
                longitude = 78.3781,
                photoBitmap = null,
                status = "On-Site Check-In",
                notes = "Assembling dining suite & chandelier alignment"
            ),
            AttendanceRecord(
                id = "ATT-03",
                staffName = "Phani Kumar",
                role = "Survey & Glazing Lead",
                timestamp = "Today, 10:05 AM",
                siteOrOffice = "Botanica Villas, Gachibowli",
                latitude = 17.4520,
                longitude = 78.3582,
                photoBitmap = null,
                status = "Field Survey",
                notes = "Taking laser window aperture dimensions"
            ),
            AttendanceRecord(
                id = "ATT-04",
                staffName = "Ravi Teja",
                role = "Senior Sales Consultant",
                timestamp = "Today, 10:00 AM",
                siteOrOffice = "Jubilee Hills Showroom",
                latitude = 17.4319,
                longitude = 78.4073,
                photoBitmap = null,
                status = "Present",
                notes = "Showroom floor sales duty & walk-in consultations"
            ),
            AttendanceRecord(
                id = "ATT-05",
                staffName = "Sirisha Reception",
                role = "Front Desk & Reception",
                timestamp = "Today, 09:45 AM",
                siteOrOffice = "Jubilee Hills Showroom",
                latitude = 17.4319,
                longitude = 78.4073,
                photoBitmap = null,
                status = "Present",
                notes = "Reception desk active & walk-in register online"
            )
        )

        // Seed WhatsApp Chat Groups
        val grp1Members = listOf(
            ChatMember("M1", "Madio Admin (You)", "Operations & MD", "+91 98480 00001", isAdmin = true),
            ChatMember("M2", "Arun Kumar", "Site PM & Civil Lead", "+91 98480 11223"),
            ChatMember("M3", "Sneha Rao", "Principal Architect", "+91 98480 33445"),
            ChatMember("M4", "Veerendra", "Installation Lead", "+91 98480 55667")
        )

        val grp2Members = listOf(
            ChatMember("M1", "Madio Admin (You)", "Operations & MD", "+91 98480 00001", isAdmin = true),
            ChatMember("M4", "Veerendra", "Installation Lead", "+91 98480 55667"),
            ChatMember("M5", "Phani Kumar", "Survey Lead", "+91 98480 77889"),
            ChatMember("M6", "Sirisha", "Client Coordinator", "+91 98480 99001")
        )

        val grp3Members = listOf(
            ChatMember("M1", "Madio Admin (You)", "Operations & MD", "+91 98480 00001", isAdmin = true),
            ChatMember("M7", "Kalyan Site PM", "Paint Specialist", "+91 99890 44552"),
            ChatMember("M8", "Vikram Mehta", "Studio Head - MAP", "+91 99890 66778")
        )

        val grp4Members = listOf(
            ChatMember("M1", "Madio Admin (You)", "Operations & MD", "+91 98480 00001", isAdmin = true),
            ChatMember("M9", "Rajesh Varma", "Commercial Director", "+91 98480 22110"),
            ChatMember("M10", "Sunil Accounts", "Head of Finance", "+91 98480 44332")
        )

        val grp5Members = listOf(
            ChatMember("M1", "Madio Admin (You)", "Operations & MD", "+91 98480 00001", isAdmin = true),
            ChatMember("M11", "Ramesh Factory Head", "Production GM", "+91 97011 22334"),
            ChatMember("M12", "Suresh CNC Lead", "Machine Operator", "+91 97011 44556")
        )

        val initialGroups = listOf(
            ChatGroup(
                id = "GRP-01",
                name = "Nanakramguda Villa - Execution & Snags",
                description = "Confidential site coordination for Shankar Reddy Villa. Shop drawings, moisture logs, BoQ updates.",
                projectId = "PRJ-01",
                projectNo = "PRJ-2026-08",
                projectName = "Shankar Reddy Villa, Nanakramguda",
                division = Division.FURNITURE,
                isConfidential = true,
                confidentialityNotice = "Strictly internal MADIO Organization. Drawings, pricing, and site discussions are confidential.",
                members = grp1Members,
                lastMessage = "Understood sir. Snagging checklist will be uploaded by 4 PM.",
                lastMessageTime = "10:15 AM",
                unreadCount = 2,
                isPinned = true,
                groupAvatarType = "PROJECT"
            ),
            ChatGroup(
                id = "GRP-02",
                name = "My Home Bhooja #402 - Fitout Hub",
                description = "Internal project team for Dr. K. Srinivas penthouse fitout and smoked oak furniture delivery.",
                projectId = "PRJ-02",
                projectNo = "PRJ-2026-09",
                projectName = "Dr. K. Srinivas - Penthouse #402",
                division = Division.FURNITURE,
                isConfidential = true,
                confidentialityNotice = "Confidential client project discussion. Do not share credentials or drawings outside team.",
                members = grp2Members,
                lastMessage = "Dispatched from Balanagar factory. Elevator padding in place.",
                lastMessageTime = "Yesterday",
                unreadCount = 0,
                isPinned = false,
                groupAvatarType = "PROJECT"
            ),
            ChatGroup(
                id = "GRP-03",
                name = "Jubilee Hills Art Gallery - MAP Plaster",
                description = "MAP Italian Marmorino lime plaster application, coats inspection, and curing logs.",
                projectId = "PRJ-03",
                projectNo = "PRJ-2026-10",
                projectName = "Tarun Chawla - Art Gallery Facade",
                division = Division.MAP,
                isConfidential = true,
                confidentialityNotice = "MAP proprietary technique & project formula discussions. Strictly confidential.",
                members = grp3Members,
                lastMessage = "Please adhere strictly to 48hr cure before beeswax buffing.",
                lastMessageTime = "Yesterday",
                unreadCount = 0,
                isPinned = false,
                groupAvatarType = "SITE"
            ),
            ChatGroup(
                id = "GRP-04",
                name = "MADIO Executive Commercials & Margins",
                description = "Strictly confidential executive board chat for purchase orders, margins, and financial authorizations.",
                projectId = null,
                projectNo = null,
                projectName = null,
                division = Division.ALL,
                isConfidential = true,
                confidentialityNotice = "STRICTLY CONFIDENTIAL. Executive & Management access only. Financial and proprietary data.",
                members = grp4Members,
                lastMessage = "Q3 hardware margin projection approved at 41.2%",
                lastMessageTime = "Sep 18",
                unreadCount = 1,
                isPinned = true,
                groupAvatarType = "MANAGEMENT"
            ),
            ChatGroup(
                id = "GRP-05",
                name = "Balanagar Factory - CNC & Woodwork Orders",
                description = "Direct liaison between showroom sales, architects, and Balanagar production factory.",
                projectId = null,
                projectNo = null,
                projectName = null,
                division = Division.FURNITURE,
                isConfidential = true,
                confidentialityNotice = "MADIO Woodworks Factory internal channel.",
                members = grp5Members,
                lastMessage = "Veneer pressing for Nanakramguda batch 1 is completed.",
                lastMessageTime = "Sep 17",
                unreadCount = 0,
                isPinned = false,
                groupAvatarType = "FACTORY"
            )
        )
        _chatGroups.value = initialGroups

        // Seed WhatsApp Chat Messages
        val grp1Messages = listOf(
            ChatMessage(
                id = "MSG-01",
                groupId = "GRP-01",
                senderName = "MADIO System",
                senderRole = "Bot",
                isFromMe = false,
                text = "🔒 Group created & securely linked to Project PRJ-2026-08 (Shankar Reddy Villa, Nanakramguda). Confidential discussions, BoQs, and architectural drawings are restricted to this internal room.",
                timestamp = "Yesterday, 09:00 AM",
                isSystemNotice = true
            ),
            ChatMessage(
                id = "MSG-02",
                groupId = "GRP-01",
                senderName = "Arun Kumar",
                senderRole = "Site PM",
                isFromMe = false,
                text = "Good morning team! Master bedroom walk-in closet framing has begun. Laser moisture probe shows 10.4%, which is well below the 12% ceiling threshold. Substrate is ready for Italian primer.",
                timestamp = "Yesterday, 09:15 AM",
                isConfidential = true
            ),
            ChatMessage(
                id = "MSG-03",
                groupId = "GRP-01",
                senderName = "Sneha Rao",
                senderRole = "Principal Architect",
                isFromMe = false,
                text = "Sharing revised elevation drawings for the walk-in wardrobe with Hafele profile clearances. Please review Section B-B carefully before the carpenters cut the veneer.",
                timestamp = "Yesterday, 10:30 AM",
                attachment = ChatAttachment(
                    id = "ATT-DOC-01",
                    type = ChatAttachmentType.DOCUMENT,
                    title = "Master_Closet_Elevations_Rev4.pdf",
                    subtitle = "Architectural CAD Export",
                    fileSize = "2.8 MB",
                    extension = "PDF",
                    documentContent = "SPECIFICATION:\n- Height: 2750mm (Floor to False Ceiling)\n- Carcass: 18mm Century Marine Ply 710 calibrated\n- Shutters: Fluted smoked ash veneer with concealed LED profile\n- Hardware: Blum Aventos HK-S lifts & Hafele Matrix drawer runners\n- Finish: 20% Polyurethane Matte Clear"
                ),
                isConfidential = true
            ),
            ChatMessage(
                id = "MSG-04",
                groupId = "GRP-01",
                senderName = "Veerendra",
                senderRole = "Installation Lead",
                isFromMe = false,
                text = "Carcass leveling completed this morning. Plinth alignment is accurate within 1.5mm tolerance across the entire 18ft run.",
                timestamp = "Today, 09:40 AM",
                attachment = ChatAttachment(
                    id = "ATT-IMG-01",
                    type = ChatAttachmentType.IMAGE,
                    title = "WalkIn_Closet_Framework_Inspection.jpg",
                    subtitle = "Site inspection photo - Master Bedroom",
                    fileSize = "1.8 MB",
                    extension = "JPG",
                    documentContent = "Inspection Checklist: Level verified using spirit level & laser grid. All fastener anchors pre-drilled. Marine plywood 710 stamp verified."
                )
            ),
            ChatMessage(
                id = "MSG-05",
                groupId = "GRP-01",
                senderName = "Madio Admin (You)",
                senderRole = "Operations & MD",
                isFromMe = true,
                text = "Excellent work team. I have approved the top-up of ₹25,000 to your Site Petty Cash wallet (Wallet PW-01) for the urgent procurement of Blum soft-close hinges and tempo unloading.",
                timestamp = "Today, 10:05 AM",
                isConfidential = true
            ),
            ChatMessage(
                id = "MSG-06",
                groupId = "GRP-01",
                senderName = "Arun Kumar",
                senderRole = "Site PM",
                isFromMe = false,
                text = "Understood sir. Snagging checklist will be uploaded by 4 PM.",
                timestamp = "Today, 10:15 AM"
            )
        )

        val grp2Messages = listOf(
            ChatMessage(
                id = "MSG-201",
                groupId = "GRP-02",
                senderName = "MADIO System",
                senderRole = "Bot",
                isFromMe = false,
                text = "🔒 Confidential internal channel linked to Project PRJ-2026-09 (Dr. K. Srinivas - My Home Bhooja #402).",
                timestamp = "Sep 18, 11:00 AM",
                isSystemNotice = true
            ),
            ChatMessage(
                id = "MSG-202",
                groupId = "GRP-02",
                senderName = "Phani Kumar",
                senderRole = "Survey Lead",
                isFromMe = false,
                text = "Client approved the smoked oak matte finish sample during his visit to the Jubilee Hills showroom yesterday.",
                timestamp = "Sep 18, 02:30 PM",
                attachment = ChatAttachment(
                    id = "ATT-IMG-02",
                    type = ChatAttachmentType.IMAGE,
                    title = "Smoked_Oak_Matte_Polyurethane_Swatch.jpg",
                    subtitle = "Client approval swatch photo",
                    fileSize = "1.4 MB",
                    extension = "JPG",
                    documentContent = "Finish: Smoked European White Oak, 5% dead matte PU, double UV coat."
                )
            ),
            ChatMessage(
                id = "MSG-203",
                groupId = "GRP-02",
                senderName = "Veerendra",
                senderRole = "Installation Lead",
                isFromMe = false,
                text = "Attached the verified hardware bill of quantities for the living room console and 8-seater dining table.",
                timestamp = "Yesterday, 11:20 AM",
                attachment = ChatAttachment(
                    id = "ATT-DOC-02",
                    type = ChatAttachmentType.DOCUMENT,
                    title = "Bhooja_Living_Dining_Hardware_BoQ.xlsx",
                    subtitle = "Itemized Hardware Breakdown",
                    fileSize = "1.2 MB",
                    extension = "XLSX",
                    documentContent = "BoQ SUMMARY:\n- 16x Blum Clip Top 110 deg soft-close hinges (₹480/pc)\n- 6x Blum Legrabox pure drawer systems 500mm (₹4,200/set)\n- 1x Custom German extruded brass table undercarriage (₹45,000)\n- 8x Italian felt glider pads for marble floor protection"
                ),
                isConfidential = true
            ),
            ChatMessage(
                id = "MSG-204",
                groupId = "GRP-02",
                senderName = "Madio Admin (You)",
                senderRole = "Operations & MD",
                isFromMe = true,
                text = "Dispatched from Balanagar factory. Elevator padding in place.",
                timestamp = "Yesterday, 04:45 PM"
            )
        )

        val grp3Messages = listOf(
            ChatMessage(
                id = "MSG-301",
                groupId = "GRP-03",
                senderName = "MADIO System",
                senderRole = "Bot",
                isFromMe = false,
                text = "🔒 Channel linked to Project PRJ-2026-10 (Tarun Chawla - Jubilee Hills Art Gallery Facade).",
                timestamp = "Sep 17, 10:00 AM",
                isSystemNotice = true
            ),
            ChatMessage(
                id = "MSG-302",
                groupId = "GRP-03",
                senderName = "Kalyan Site PM",
                senderRole = "Paint Specialist",
                isFromMe = false,
                text = "Second coat of Italian Venetian stucco completed across the 4,000 sq ft double-height atrium.",
                timestamp = "Sep 18, 04:10 PM",
                attachment = ChatAttachment(
                    id = "ATT-IMG-03",
                    type = ChatAttachmentType.IMAGE,
                    title = "Gallery_Atrium_Venetian_Stucco_Coat2.jpg",
                    subtitle = "Italian Marmorino lime plaster inspection",
                    fileSize = "2.1 MB",
                    extension = "JPG",
                    documentContent = "Application specs: 2nd coat applied using stainless steel Venetian trowel with 30-degree burnishing."
                )
            ),
            ChatMessage(
                id = "MSG-303",
                groupId = "GRP-03",
                senderName = "Vikram Mehta",
                senderRole = "Studio Head - MAP",
                isFromMe = false,
                text = "Please adhere strictly to 48hr cure before beeswax buffing.",
                timestamp = "Yesterday, 09:30 AM",
                attachment = ChatAttachment(
                    id = "ATT-DOC-03",
                    type = ChatAttachmentType.DOCUMENT,
                    title = "MAP_Italian_Lime_Plaster_TDS_Spec.pdf",
                    subtitle = "Technical Data Sheet & Application Guide",
                    fileSize = "3.4 MB",
                    extension = "PDF",
                    documentContent = "TECHNICAL DATA SHEET:\n- Composition: Aged Slaked Lime, Micronized Carrara Marble Powder\n- VOC: < 0.1 g/L (Zero VOC)\n- Curing requirement: Minimum 48 hours at 25-30 deg C before wax buffing\n- Breathability: High water vapor permeability (Sd = 0.04m)"
                ),
                isConfidential = true
            )
        )

        val grp4Messages = listOf(
            ChatMessage(
                id = "MSG-401",
                groupId = "GRP-04",
                senderName = "MADIO System",
                senderRole = "Bot",
                isFromMe = false,
                text = "🔒 STRICTLY CONFIDENTIAL. Executive & Management access only. Financial negotiations, margins, and proprietary data.",
                timestamp = "Sep 15, 09:00 AM",
                isSystemNotice = true
            ),
            ChatMessage(
                id = "MSG-402",
                groupId = "GRP-04",
                senderName = "Rajesh Varma",
                senderRole = "Commercial Director",
                isFromMe = false,
                text = "We have concluded the direct container import pricing with Blum Austria. Expected landing cost reduction is 14.8% on all tandem runners.",
                timestamp = "Sep 17, 03:15 PM",
                isConfidential = true
            ),
            ChatMessage(
                id = "MSG-403",
                groupId = "GRP-04",
                senderName = "Madio Admin (You)",
                senderRole = "Operations & MD",
                isFromMe = true,
                text = "Q3 hardware margin projection approved at 41.2%",
                timestamp = "Sep 18, 05:00 PM",
                isConfidential = true
            )
        )

        val grp5Messages = listOf(
            ChatMessage(
                id = "MSG-501",
                groupId = "GRP-05",
                senderName = "MADIO System",
                senderRole = "Bot",
                isFromMe = false,
                text = "🔒 MADIO Woodworks Balanagar Factory Production liaison.",
                timestamp = "Sep 15, 08:00 AM",
                isSystemNotice = true
            ),
            ChatMessage(
                id = "MSG-502",
                groupId = "GRP-05",
                senderName = "Ramesh Factory Head",
                senderRole = "Production GM",
                isFromMe = false,
                text = "Veneer pressing for Nanakramguda batch 1 is completed.",
                timestamp = "Sep 17, 11:30 AM"
            )
        )

        _chatMessages.value = mapOf(
            "GRP-01" to grp1Messages,
            "GRP-02" to grp2Messages,
            "GRP-03" to grp3Messages,
            "GRP-04" to grp4Messages,
            "GRP-05" to grp5Messages
        )
    }
}

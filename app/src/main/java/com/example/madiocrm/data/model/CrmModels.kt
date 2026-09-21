package com.example.madiocrm.data.model

import android.graphics.Bitmap

enum class Division(val id: String, val displayName: String, val shortCode: String, val colorHex: Long) {
    ALL("all", "All Brands", "ALL", 0xFF0062D2),
    FURNITURE("furniture", "Madio Furniture", "MF", 0xFFC9A84C),
    MAP("map", "MAP Premium Paints", "MAP", 0xFF2D9A5F),
    DW("dw", "Doors & Windows", "DW", 0xFF2A72B8)
}

enum class LeadStage(val displayName: String) {
    NEW("New"),
    CONTACTED("Contacted"),
    SURVEY_NEEDED("Survey Needed"),
    QUALIFIED("Qualified"),
    QUOTED("Quoted"),
    WON("Won"),
    LOST("Lost")
}

data class Visitor(
    val id: String,
    val visitorNo: String,
    val name: String,
    val phone: String,
    val email: String = "",
    val purpose: String = "Showroom Walk-in",
    val division: Division = Division.FURNITURE,
    val interestedIn: String = "",
    val attendedBy: String = "Front Desk",
    val checkInTime: String = "Today, 11:30 AM",
    val status: String = "Inquiry Logged", // "Inquiry Logged", "Converted to Lead", "Direct Purchase"
    val convertedLeadId: String? = null,
    val notes: String = ""
)

data class SiteSurvey(
    val id: String,
    val surveyNo: String,
    val leadId: String = "",
    val clientName: String,
    val phone: String,
    val siteAddress: String,
    val division: Division = Division.FURNITURE,
    val surveyDate: String,
    val engineerName: String,
    val measurements: String,
    val moistureLevel: String = "Normal (< 12%)",
    val apertureCount: Int = 4,
    val wallAreaSqft: Double = 0.0,
    val notes: String = "",
    val photoCount: Int = 4,
    val status: String = "Scheduled", // "Scheduled", "Completed", "Quote Generated"
    val linkedQuoteId: String? = null
)

data class Lead(
    val id: String,
    val name: String,
    val phone: String,
    val source: String, // "Instagram", "Architect", "Walk-in Visitor", "Referral", "Website"
    val reference: String = "",
    val division: Division = Division.FURNITURE,
    val stage: LeadStage = LeadStage.NEW,
    val followUpDate: String = "",
    val remarks: String = "",
    val estimatedValue: Double = 0.0,
    val confidenceLevel: Int = 70, // 0-100%
    val assignedTo: String = "Sales Team",
    val createdAt: String = "",
    val visitorId: String? = null,
    val surveyId: String? = null,
    val quoteId: String? = null
)

enum class DealStage(val displayName: String) {
    DISCOVERY("Discovery"),
    SITE_VISIT("Site Visit"),
    DESIGN_QUOTE("Design & Quote"),
    NEGOTIATION("Negotiation"),
    WON("Won"),
    LOST("Lost")
}

data class QuoteLineItem(
    val id: String,
    val description: String,
    val sku: String = "",
    val qty: Double = 1.0,
    val unit: String = "pcs",
    val rate: Double = 0.0,
    val discountPct: Double = 0.0,
    val taxPct: Double = 18.0
) {
    val subtotal: Double get() = qty * rate * (1.0 - discountPct / 100.0)
    val taxAmount: Double get() = subtotal * (taxPct / 100.0)
    val total: Double get() = subtotal + taxAmount
}

data class Quote(
    val id: String,
    val quoteNo: String,
    val date: String,
    val customerName: String,
    val phone: String,
    val division: Division = Division.FURNITURE,
    val stage: DealStage = DealStage.DESIGN_QUOTE,
    val lineItems: List<QuoteLineItem> = emptyList(),
    val remarks: String = "",
    val byUser: String = "Sales Rep",
    val isApproved: Boolean = true
) {
    val subtotal: Double get() = lineItems.sumOf { it.subtotal }
    val taxTotal: Double get() = lineItems.sumOf { it.taxAmount }
    val grandTotal: Double get() = lineItems.sumOf { it.total }
}

enum class SaleStatus(val displayName: String) {
    PENDING("Pending"),
    PARTIAL("Partial"),
    PAID("Paid")
}

data class SaleOrder(
    val id: String,
    val saleNo: String,
    val date: String,
    val customerName: String,
    val division: Division = Division.FURNITURE,
    val quoteRef: String = "",
    val totalValue: Double = 0.0,
    val paidAmount: Double = 0.0,
    val deliveryDate: String = "",
    val status: SaleStatus = SaleStatus.PENDING,
    val remarks: String = ""
) {
    val balanceDue: Double get() = (totalValue - paidAmount).coerceAtLeast(0.0)
}

data class Milestone(
    val title: String,
    val completed: Boolean,
    val completedAt: String = ""
)

data class Project(
    val id: String,
    val projectNo: String,
    val customerName: String,
    val phone: String,
    val division: Division,
    val contractValue: Double,
    val paidAmount: Double,
    val stage: String, // "Site Survey", "Execution", "Snagging", "Handover", "Completed"
    val completionPct: Int,
    val siteAddress: String,
    val assignedEngineer: String,
    val targetDate: String,
    val milestones: List<Milestone> = emptyList(),
    val dailyLogCount: Int = 0,
    val walletId: String? = null
)

data class ProjectWallet(
    val id: String,
    val projectId: String,
    val projectNo: String,
    val projectName: String,
    val clientName: String,
    val division: Division,
    val totalAllocated: Double,
    val totalSpent: Double,
    val engineerName: String
) {
    val balance: Double get() = (totalAllocated - totalSpent).coerceAtLeast(0.0)
    val utilizationPct: Int get() = if (totalAllocated > 0) ((totalSpent / totalAllocated) * 100).toInt() else 0
}

data class ProjectExpense(
    val id: String,
    val walletId: String,
    val projectId: String,
    val projectNo: String,
    val date: String,
    val amount: Double,
    val category: String, // "Hardware/Fasteners", "Conveyance/Fuel", "Daily Labour Advance", "Tempo Freight/Unloading", "Site Refreshments", "Consumables"
    val description: String,
    val paidTo: String,
    val approved: Boolean = true
)

data class AttendanceRecord(
    val id: String,
    val staffName: String,
    val role: String, // "Site Engineer", "Sales Consultant", "Installation Lead", "Showroom Manager"
    val timestamp: String,
    val siteOrOffice: String,
    val latitude: Double,
    val longitude: Double,
    val photoBitmap: Bitmap? = null,
    val status: String = "Present", // "Present", "On-Site Check-In", "Field Survey"
    val notes: String = ""
)

data class InventoryItem(
    val id: String,
    val sku: String,
    val name: String,
    val category: String,
    val vendor: String,
    val qty: Int,
    val costPrice: Double,
    val mrp: Double,
    val marginPct: Double,
    val status: String, // "In Stock", "Low Stock", "Display", "Reserved"
    val location: String, // "Showroom", "Warehouse Floor 1", "Warehouse Floor 2"
    val division: Division = Division.FURNITURE
)

data class TaxInvoice(
    val id: String,
    val invoiceNo: String,
    val date: String,
    val customerName: String,
    val phone: String,
    val subtotal: Double,
    val gstRate: Double = 18.0,
    val totalAmount: Double,
    val paidAmount: Double,
    val status: String // "Paid", "Partially Paid", "Overdue"
) {
    val balance: Double get() = (totalAmount - paidAmount).coerceAtLeast(0.0)
}

data class PettyCashEntry(
    val id: String,
    val date: String,
    val type: String, // "IN" or "OUT"
    val category: String, // "Hardware", "Fuel", "Refreshments", "Transport", "Advance"
    val amount: Double,
    val description: String,
    val party: String,
    val approved: Boolean = true
)

data class Customer(
    val id: String,
    val name: String,
    val phone: String,
    val email: String = "",
    val address: String = "",
    val division: Division = Division.FURNITURE,
    val stage: String = "Active", // "Prospect", "Active", "Dormant"
    val lifetimeValue: Double = 0.0,
    val totalOrders: Int = 1
)

data class Architect(
    val id: String,
    val name: String,
    val firm: String,
    val phone: String,
    val location: String,
    val commissionRate: Double = 5.0,
    val projectsReferred: Int = 3
)

enum class TaskPriority {
    LOW, MEDIUM, HIGH, URGENT
}

data class TaskItem(
    val id: String,
    val title: String,
    val priority: TaskPriority = TaskPriority.MEDIUM,
    val dueDate: String,
    val category: String = "Follow-up",
    val isDone: Boolean = false,
    val relatedTo: String = ""
)

enum class ChatAttachmentType {
    IMAGE, DOCUMENT, VOICE, LOCATION
}

data class ChatAttachment(
    val id: String = java.util.UUID.randomUUID().toString(),
    val type: ChatAttachmentType = ChatAttachmentType.DOCUMENT,
    val title: String,
    val subtitle: String = "",
    val fileSize: String = "",
    val extension: String = "", // "PDF", "DWG", "XLSX", "JPG", "PNG"
    val localBitmap: Bitmap? = null,
    val previewUrl: String = "",
    val documentContent: String = "" // preview text / summary for documents
)

enum class MessageStatus {
    SENT, DELIVERED, READ
}

data class ChatMessage(
    val id: String = java.util.UUID.randomUUID().toString(),
    val groupId: String,
    val senderName: String,
    val senderRole: String,
    val isFromMe: Boolean,
    val text: String,
    val timestamp: String,
    val attachment: ChatAttachment? = null,
    val isConfidential: Boolean = false,
    val isSystemNotice: Boolean = false,
    val status: MessageStatus = MessageStatus.READ
)

data class ChatMember(
    val id: String,
    val name: String,
    val role: String,
    val phone: String,
    val isOnline: Boolean = true,
    val isAdmin: Boolean = false
)

data class ChatGroup(
    val id: String,
    val name: String,
    val description: String,
    val projectId: String? = null, // Linked Project ID
    val projectNo: String? = null,
    val projectName: String? = null,
    val division: Division = Division.ALL,
    val isConfidential: Boolean = true,
    val confidentialityNotice: String = "Strictly internal MADIO Organization. Drawings, pricing, and site discussions are confidential.",
    val members: List<ChatMember> = emptyList(),
    val lastMessage: String = "",
    val lastMessageTime: String = "",
    val unreadCount: Int = 0,
    val isPinned: Boolean = false,
    val groupAvatarType: String = "PROJECT" // "PROJECT", "FACTORY", "MANAGEMENT", "SITE"
)

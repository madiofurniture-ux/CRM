package com.example.madiocrm.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.madiocrm.data.model.DealStage
import com.example.madiocrm.data.model.Division
import com.example.madiocrm.data.model.LeadStage
import com.example.madiocrm.ui.theme.*
import java.text.NumberFormat
import java.util.Locale

fun formatInr(amount: Double): String {
    val formatter = NumberFormat.getCurrencyInstance(Locale("en", "IN"))
    formatter.maximumFractionDigits = 0
    return formatter.format(amount)
}

@Composable
fun DivisionBadge(division: Division, modifier: Modifier = Modifier) {
    val (bg, fg) = when (division) {
        Division.FURNITURE -> GoldLight to Color(0xFF8A6C12)
        Division.MAP -> SuccessGreenLight to Color(0xFF0F766E)
        Division.DW -> AuraBlueLight to AuraBlueDark
        Division.ALL -> Slate100 to Slate700
    }
    Surface(
        color = bg,
        shape = RoundedCornerShape(6.dp),
        modifier = modifier
    ) {
        Text(
            text = division.shortCode,
            color = fg,
            style = MaterialTheme.typography.labelMedium,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
        )
    }
}

@Composable
fun LeadStageBadge(stage: LeadStage, modifier: Modifier = Modifier) {
    val (bg, fg) = when (stage) {
        LeadStage.NEW -> Color(0xFFEFF6FF) to Color(0xFF1D4ED8)
        LeadStage.CONTACTED -> Color(0xFFF3E8FF) to Color(0xFF7E22CE)
        LeadStage.SURVEY_NEEDED -> Color(0xFFE0E7FF) to Color(0xFF4338CA)
        LeadStage.QUALIFIED -> Color(0xFFFEF3C7) to Color(0xFFB45309)
        LeadStage.QUOTED -> Color(0xFFE0F2FE) to Color(0xFF0369A1)
        LeadStage.WON -> SuccessGreenLight to Color(0xFF047857)
        LeadStage.LOST -> DangerRedLight to Color(0xFFB91C1C)
    }
    Surface(
        color = bg,
        shape = RoundedCornerShape(12.dp),
        modifier = modifier
    ) {
        Text(
            text = stage.displayName,
            color = fg,
            style = MaterialTheme.typography.labelMedium,
            fontWeight = FontWeight.SemiBold,
            modifier = Modifier.padding(horizontal = 8.dp, vertical = 3.dp)
        )
    }
}

@Composable
fun DealStageBadge(stage: DealStage, modifier: Modifier = Modifier) {
    val (bg, fg) = when (stage) {
        DealStage.DISCOVERY -> Slate100 to Slate700
        DealStage.SITE_VISIT -> Color(0xFFE0E7FF) to Color(0xFF4338CA)
        DealStage.DESIGN_QUOTE -> Color(0xFFE0F2FE) to Color(0xFF0369A1)
        DealStage.NEGOTIATION -> WarningAmberLight to Color(0xFFB45309)
        DealStage.WON -> SuccessGreenLight to Color(0xFF047857)
        DealStage.LOST -> DangerRedLight to Color(0xFFB91C1C)
    }
    Surface(
        color = bg,
        shape = RoundedCornerShape(12.dp),
        modifier = modifier
    ) {
        Text(
            text = stage.displayName,
            color = fg,
            style = MaterialTheme.typography.labelMedium,
            fontWeight = FontWeight.SemiBold,
            modifier = Modifier.padding(horizontal = 8.dp, vertical = 3.dp)
        )
    }
}

@Composable
fun DivisionFilterRow(
    selectedDivision: Division,
    onSelect: (Division) -> Unit,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .horizontalScroll(rememberScrollState())
            .padding(horizontal = 16.dp, vertical = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        Division.values().forEach { division ->
            val isSelected = selectedDivision == division
            FilterChip(
                selected = isSelected,
                onClick = { onSelect(division) },
                label = { Text(division.displayName) },
                colors = FilterChipDefaults.filterChipColors(
                    selectedContainerColor = AuraBlue,
                    selectedLabelColor = Color.White,
                    containerColor = Color.White,
                    labelColor = Slate700
                ),
                shape = RoundedCornerShape(20.dp),
                modifier = Modifier.testTag("filter_chip_${division.id}")
            )
        }
    }
}

@Composable
fun KpiCard(
    title: String,
    value: String,
    subtitle: String,
    icon: ImageVector,
    iconBgColor: Color,
    iconTint: Color,
    modifier: Modifier = Modifier
) {
    Card(
        colors = CardDefaults.cardColors(containerColor = Color.White),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
        shape = RoundedCornerShape(16.dp),
        modifier = modifier
    ) {
        Column(
            modifier = Modifier.padding(14.dp)
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween,
                modifier = Modifier.fillMaxWidth()
            ) {
                Text(
                    text = title,
                    style = MaterialTheme.typography.labelMedium,
                    color = Slate500
                )
                Box(
                    modifier = Modifier
                        .size(32.dp)
                        .clip(CircleShape)
                        .background(iconBgColor),
                    contentAlignment = Alignment.Center
                ) {
                    Icon(
                        imageVector = icon,
                        contentDescription = null,
                        tint = iconTint,
                        modifier = Modifier.size(18.dp)
                    )
                }
            }
            Spacer(modifier = Modifier.height(6.dp))
            Text(
                text = value,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                color = Slate900
            )
            Spacer(modifier = Modifier.height(2.dp))
            Text(
                text = subtitle,
                style = MaterialTheme.typography.bodySmall,
                color = Slate500,
                fontSize = 11.sp
            )
        }
    }
}

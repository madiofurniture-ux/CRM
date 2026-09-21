package com.example.madiocrm.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val LightColorScheme = lightColorScheme(
    primary = AuraBlue,
    onPrimary = Color.White,
    primaryContainer = AuraBlueLight,
    onPrimaryContainer = AuraBlueDark,
    secondary = GoldAccent,
    onSecondary = Color.White,
    secondaryContainer = GoldLight,
    onSecondaryContainer = Color(0xFF5C4700),
    tertiary = SuccessGreen,
    onTertiary = Color.White,
    tertiaryContainer = SuccessGreenLight,
    onTertiaryContainer = Color(0xFF065F46),
    background = Slate50,
    onBackground = Slate900,
    surface = Color.White,
    onSurface = Slate900,
    surfaceVariant = Slate100,
    onSurfaceVariant = Slate600,
    outline = Slate300
)

@Composable
fun MadioCrmTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = LightColorScheme,
        typography = Typography,
        content = content
    )
}

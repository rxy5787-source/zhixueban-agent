import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    // AGP 9.1 supplies Kotlin 2.2.10; do not also apply kotlin-android.
    alias(libs.plugins.kotlin.compose)
}

// Per-computer development endpoints survive a normal Android Studio rebuild.
// Release endpoints must still be supplied explicitly and require HTTPS at runtime.
val phoneServices = Properties().apply {
    val source = rootProject.file("phone-services.local.properties")
    if (source.isFile) source.inputStream().use { load(it) }
}

android {
    namespace = "com.example.adaptive_quiz_app"
    compileSdk {
        version = release(36) {
            minorApiLevel = 1
        }
    }

    defaultConfig {
        applicationId = "com.example.adaptive_quiz_app"
        minSdk = 24
        targetSdk = 36
        versionCode = 1
        versionName = "1.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildTypes {
        debug {
            buildConfigField("String", "AI_BASE_URL", "\"${providers.gradleProperty("ai.baseUrl").orElse(phoneServices.getProperty("ai.baseUrl", "http://127.0.0.1:8000")).get()}\"")
            buildConfigField("String", "AUTH_BASE_URL", "\"${providers.gradleProperty("auth.baseUrl").orElse(phoneServices.getProperty("auth.baseUrl", "http://127.0.0.1:8087")).get()}\"")
        }
        release {
            buildConfigField("String", "AI_BASE_URL", "\"${providers.gradleProperty("ai.baseUrl").orElse("").get()}\"")
            buildConfigField("String", "AUTH_BASE_URL", "\"${providers.gradleProperty("auth.baseUrl").orElse("").get()}\"")
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_11)
    }
}

dependencies {
    val composeBom = platform(libs.compose.bom)
    implementation(composeBom)
    androidTestImplementation(composeBom)
    implementation(libs.compose.ui)
    implementation(libs.compose.foundation)
    implementation(libs.compose.material3)
    implementation(libs.compose.tooling.preview)
    debugImplementation(libs.compose.tooling)
    androidTestImplementation(libs.compose.test.junit4)

    val roomVersion = "2.6.1"
    implementation("androidx.room:room-runtime:$roomVersion")
    annotationProcessor("androidx.room:room-compiler:$roomVersion")

    implementation(libs.appcompat)
    implementation(libs.material)
    implementation(libs.activity)
    implementation(libs.constraintlayout)
    testImplementation(libs.junit)
    androidTestImplementation(libs.ext.junit)
    androidTestImplementation(libs.espresso.core)
}

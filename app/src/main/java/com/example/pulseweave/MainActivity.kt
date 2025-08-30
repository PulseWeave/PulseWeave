package com.example.pulseweave

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.tooling.preview.Preview
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import com.example.pulseweave.ui.theme.PulseWeaveTheme

class MainActivity : ComponentActivity() {

    companion object {
        const val PERMISSION_REQUEST_CODE = 1
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        // 动态权限检查和请求
        if (!checkPermissions()) {
            requestPermissions()
        } else {
            // 权限已授权，执行相关操作
            setupUI()
        }
    }

    private fun checkPermissions(): Boolean {
        val wifiPermission = ContextCompat.checkSelfPermission(
            this, Manifest.permission.ACCESS_WIFI_STATE
        ) == PackageManager.PERMISSION_GRANTED
        val bluetoothPermission = ContextCompat.checkSelfPermission(
            this, Manifest.permission.BLUETOOTH
        ) == PackageManager.PERMISSION_GRANTED
        val fineLocationPermission = ContextCompat.checkSelfPermission(
            this, Manifest.permission.ACCESS_FINE_LOCATION
        ) == PackageManager.PERMISSION_GRANTED

        return wifiPermission && bluetoothPermission && fineLocationPermission
    }

    private fun requestPermissions() {
        ActivityCompat.requestPermissions(
            this,
            arrayOf(
                Manifest.permission.INTERNET,
                Manifest.permission.ACCESS_WIFI_STATE,
                Manifest.permission.BLUETOOTH,
                Manifest.permission.BLUETOOTH_ADMIN,
                Manifest.permission.ACCESS_FINE_LOCATION
            ),
            PERMISSION_REQUEST_CODE
        )
    }

    @Deprecated("This method has been deprecated in favor of using the Activity Result API\n      which brings increased type safety via an {@link ActivityResultContract} and the prebuilt\n      contracts for common intents available in\n      {@link androidx.activity.result.contract.ActivityResultContracts}, provides hooks for\n      testing, and allow receiving results in separate, testable classes independent from your\n      activity. Use\n      {@link #registerForActivityResult(ActivityResultContract, ActivityResultCallback)} passing\n      in a {@link RequestMultiplePermissions} object for the {@link ActivityResultContract} and\n      handling the result in the {@link ActivityResultCallback#onActivityResult(Object) callback}.")
    override fun onRequestPermissionsResult(
        requestCode: Int, permissions: Array<String>, grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)

        if (requestCode == PERMISSION_REQUEST_CODE) {
            if (grantResults.all { it == PackageManager.PERMISSION_GRANTED }) {
                // 权限都已授权，执行相关操作
                setupUI()
            } else {
                // 提示用户权限未授权
                Toast.makeText(this, "权限未授权，无法继续操作", Toast.LENGTH_SHORT).show()
            }
        }
    }

    private fun setupUI() {
        setContent {
            PulseWeaveTheme {
                Scaffold(modifier = Modifier.fillMaxSize()) { innerPadding ->
                    Greeting(
                        name = "Android",
                        modifier = Modifier.padding(innerPadding)
                    )
                }
            }
        }
    }
}

@Composable
fun Greeting(name: String, modifier: Modifier = Modifier) {
    Text(
        text = "Hello $name!",
        modifier = modifier
    )
}

@Preview(showBackground = true)
@Composable
fun GreetingPreview() {
    PulseWeaveTheme {
        Greeting("Android")
    }
}

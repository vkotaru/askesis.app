package app.askesis.ui.screens

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.PhotoLibrary
import app.askesis.ui.components.AppCard as Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.SmallFloatingActionButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import androidx.compose.runtime.LaunchedEffect
import coil.compose.AsyncImage
import app.askesis.data.local.entity.PhotoEntity
import app.askesis.data.repo.AskesisRepository
import app.askesis.ui.components.prettyDate
import app.askesis.ui.components.today
import app.askesis.ui.repository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

private val VIEWS = listOf("front" to "Front", "side" to "Side", "back" to "Back")

class PhotosViewModel(private val repo: AskesisRepository) : ViewModel() {
    val photos = repo.observePhotos()

    fun save(bytes: ByteArray, view: String) = viewModelScope.launch {
        repo.savePhoto(bytes, today(), view)
    }

    fun delete(uid: String) = viewModelScope.launch { repo.deletePhoto(uid) }

    suspend fun resolve(uid: String): String? = repo.ensurePhotoFile(uid)

    companion object {
        val Factory = viewModelFactory { initializer { PhotosViewModel(repository()) } }
    }
}

@Composable
fun PhotosScreen(vm: PhotosViewModel = viewModel(factory = PhotosViewModel.Factory)) {
    val context = LocalContext.current
    val all by vm.photos.collectAsState(initial = emptyList())
    var view by remember { mutableStateOf("front") }

    val shown = remember(all, view) { all.filter { it.view == view } }

    // Camera capture writes a JPEG to this temp file via a FileProvider content URI.
    var pendingCapture by remember { mutableStateOf<File?>(null) }
    val cameraLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.TakePicture()
    ) { ok ->
        val file = pendingCapture
        if (ok && file != null && file.exists()) {
            vm.viewModelScope.launch {
                val bytes = withContext(Dispatchers.IO) { file.readBytes().also { file.delete() } }
                vm.save(bytes, view)
            }
        }
        pendingCapture = null
    }

    val galleryLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.GetContent()
    ) { uri: Uri? ->
        if (uri != null) {
            vm.viewModelScope.launch {
                val bytes = withContext(Dispatchers.IO) {
                    context.contentResolver.openInputStream(uri)?.use { it.readBytes() }
                }
                if (bytes != null) vm.save(bytes, view)
            }
        }
    }

    fun launchCamera() {
        val dir = File(context.cacheDir, "capture").apply { mkdirs() }
        val file = File(dir, "cap_${shown.size}_${view}.jpg")
        pendingCapture = file
        val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
        cameraLauncher.launch(uri)
    }

    Box(Modifier.fillMaxSize()) {
        Column(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                VIEWS.forEach { (value, label) ->
                    FilterChip(selected = view == value, onClick = { view = value }, label = { Text(label) })
                }
            }

            if (shown.isEmpty()) {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text(
                        "No $view photos yet.\nTap the camera to add one.",
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }
            } else {
                LazyVerticalGrid(
                    columns = GridCells.Fixed(2),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    items(shown, key = { it.uid }) { photo ->
                        PhotoCell(photo, onDelete = { vm.delete(photo.uid) }, resolve = { vm.resolve(it) })
                    }
                }
            }
        }

        Column(
            Modifier.align(Alignment.BottomEnd).padding(16.dp),
            horizontalAlignment = Alignment.End,
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            SmallFloatingActionButton(onClick = { galleryLauncher.launch("image/*") }) {
                Icon(Icons.Filled.PhotoLibrary, contentDescription = "Pick from gallery")
            }
            ExtendedFloatingActionButton(
                onClick = { launchCamera() },
                icon = { Icon(Icons.Filled.CameraAlt, contentDescription = null) },
                text = { Text("Capture") },
            )
        }
    }
}

@Composable
private fun PhotoCell(
    photo: PhotoEntity,
    onDelete: () -> Unit,
    resolve: suspend (String) -> String?,
) {
    // Prefer the cached local file; if it's a cloud-only row, download lazily.
    var path by remember(photo.uid) { mutableStateOf(photo.localPath) }
    LaunchedEffect(photo.uid, photo.localPath) {
        if (path == null && photo.driveFileId != null) path = resolve(photo.uid)
    }

    Card {
        Box(Modifier.fillMaxWidth().aspectRatio(0.8f)) {
            if (path != null) {
                AsyncImage(
                    model = File(path!!),
                    contentDescription = "${photo.view} on ${photo.date}",
                    contentScale = ContentScale.Crop,
                    modifier = Modifier.fillMaxSize(),
                )
            } else {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator()
                }
            }
            IconButton(
                onClick = onDelete,
                modifier = Modifier.align(Alignment.TopEnd),
            ) {
                Icon(Icons.Filled.Close, contentDescription = "Delete", tint = MaterialTheme.colorScheme.error)
            }
            Text(
                prettyDate(photo.date),
                style = MaterialTheme.typography.labelSmall,
                modifier = Modifier.align(Alignment.BottomStart).padding(6.dp),
            )
        }
    }
}

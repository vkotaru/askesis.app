package app.askesis.ui.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.LocalFireDepartment
import androidx.compose.material.icons.filled.Remove
import androidx.compose.material.icons.filled.Restaurant
import androidx.compose.material3.AlertDialog
import app.askesis.ui.components.AppCard as Card
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import app.askesis.data.local.entity.FoodEntity
import app.askesis.data.local.entity.MealEntity
import app.askesis.data.model.MealFoodItem
import app.askesis.data.model.Structured
import app.askesis.data.prefs.SettingsStore
import app.askesis.data.repo.AskesisRepository
import app.askesis.ui.components.DateNavBar
import app.askesis.ui.components.IconBadge
import app.askesis.ui.components.NumberField
import app.askesis.ui.components.PlainField
import app.askesis.ui.components.SectionHeader
import app.askesis.ui.theme.Accent
import app.askesis.ui.components.toDoubleOrNullSafe
import app.askesis.ui.components.toIntOrNullSafe
import app.askesis.ui.components.today
import app.askesis.ui.repository
import kotlinx.coroutines.launch

class NutritionViewModel(private val repo: AskesisRepository) : ViewModel() {
    var date by mutableStateOf(today()); private set
    val foods = repo.observeFoods()
    val settings = repo.settings.settings

    fun mealsFor(d: String) = repo.observeMealsForDate(d)

    fun changeDate(d: String) { date = d }

    fun upsertMeal(
        uid: String, label: String, time: String, calories: String, description: String,
        items: List<MealFoodItem>,
    ) = viewModelScope.launch {
        val totals = Structured.totals(items)
        val hasItems = items.isNotEmpty()
        repo.saveMeal(
            MealEntity(
                uid = uid, date = date, label = label,
                time = time.ifBlank { null },
                calories = if (hasItems) totals.calories.toInt() else calories.toIntOrNullSafe(),
                description = description.ifBlank { null },
                foodItemsJson = Structured.encodeFoodItems(items),
                computedCalories = if (hasItems) totals.calories else null,
                computedProteinG = if (hasItems) totals.proteinG else null,
                computedCarbsG = if (hasItems) totals.carbsG else null,
                computedFatG = if (hasItems) totals.fatG else null,
            )
        )
    }

    fun deleteMeal(uid: String) = viewModelScope.launch { repo.deleteMeal(uid) }

    fun addFood(name: String, brand: String, calories: String, protein: String, carbs: String, fat: String) =
        viewModelScope.launch {
            repo.saveFood(
                FoodEntity(
                    uid = "", name = name, brand = brand.ifBlank { null },
                    calories = calories.toDoubleOrNullSafe(),
                    proteinG = protein.toDoubleOrNullSafe(),
                    carbsG = carbs.toDoubleOrNullSafe(),
                    fatG = fat.toDoubleOrNullSafe(),
                )
            )
        }

    fun deleteFood(uid: String) = viewModelScope.launch { repo.deleteFood(uid) }

    companion object {
        val Factory = viewModelFactory { initializer { NutritionViewModel(repository()) } }
    }
}

@Composable
fun NutritionScreen(vm: NutritionViewModel = viewModel(factory = NutritionViewModel.Factory)) {
    var tab by remember { mutableStateOf(0) }
    Column(Modifier.fillMaxSize()) {
        TabRow(selectedTabIndex = tab) {
            Tab(selected = tab == 0, onClick = { tab = 0 }, text = { Text("Meals") })
            Tab(selected = tab == 1, onClick = { tab = 1 }, text = { Text("Foods") })
        }
        Box(Modifier.fillMaxSize()) {
            if (tab == 0) MealsTab(vm) else FoodsTab(vm)
        }
    }
}

@Composable
private fun MealsTab(vm: NutritionViewModel) {
    val meals by remember(vm.date) { vm.mealsFor(vm.date) }.collectAsState(initial = emptyList())
    val foods by vm.foods.collectAsState(initial = emptyList())
    val settings by vm.settings.collectAsState(initial = SettingsStore.Settings())
    var showAdd by remember { mutableStateOf(false) }
    var editing by remember { mutableStateOf<MealEntity?>(null) }

    Box(Modifier.fillMaxSize()) {
        val total = meals.sumOf { it.calories ?: 0 }
        val protein = meals.sumOf { it.computedProteinG ?: 0.0 }.toInt()
        Column(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            DateNavBar(vm.date, { vm.changeDate(it) }, hasData = meals.isNotEmpty())
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    SectionHeader(Icons.Filled.LocalFireDepartment, "Today's nutrition", Accent.Nutrition)
                    val calorieLine = if (settings.calorieTarget > 0) "$total / ${settings.calorieTarget} kcal" else "$total kcal"
                    Text(calorieLine, style = MaterialTheme.typography.headlineSmall, fontWeight = androidx.compose.ui.text.font.FontWeight.Bold)
                    if (settings.proteinTarget > 0) {
                        Text("Protein $protein / ${settings.proteinTarget} g", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
            if (meals.isEmpty()) {
                Text("No meals logged on this day.", style = MaterialTheme.typography.bodyMedium)
            } else {
                LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    items(meals, key = { it.uid }) { m ->
                        Card(Modifier.fillMaxWidth()) {
                            Row(Modifier.fillMaxWidth().padding(16.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                                IconBadge(Icons.Filled.Restaurant, Accent.Nutrition)
                                Column(Modifier.weight(1f)) {
                                    Text(m.label, style = MaterialTheme.typography.titleMedium)
                                    val sub = listOfNotNull(m.time, m.calories?.let { "$it kcal" }, m.description)
                                    if (sub.isNotEmpty()) Text(sub.joinToString(" · "), style = MaterialTheme.typography.bodySmall)
                                    val mealItems = Structured.decodeFoodItems(m.foodItemsJson)
                                    if (mealItems.isNotEmpty()) {
                                        Text(
                                            mealItems.joinToString(", ") {
                                                it.name + (if (it.quantity != 1.0) " ×${trimNum(it.quantity)}" else "")
                                            },
                                            style = MaterialTheme.typography.bodySmall,
                                        )
                                    }
                                }
                                IconButton(onClick = { editing = m }) {
                                    Icon(Icons.Filled.Edit, contentDescription = "Edit")
                                }
                                IconButton(onClick = { vm.deleteMeal(m.uid) }) {
                                    Icon(Icons.Filled.Delete, contentDescription = "Delete")
                                }
                            }
                        }
                    }
                }
            }
        }
        FloatingActionButton(
            onClick = { showAdd = true },
            modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp),
        ) { Icon(Icons.Filled.Add, contentDescription = "Add meal") }
    }

    if (showAdd || editing != null) {
        val current = editing
        key(current?.uid) {
            MealDialog(
                initial = current,
                foods = foods,
                onDismiss = { showAdd = false; editing = null },
                onSave = { uid, label, time, calories, desc, items ->
                    vm.upsertMeal(uid, label, time, calories, desc, items)
                    showAdd = false; editing = null
                },
            )
        }
    }
}

@Composable
private fun MealDialog(
    initial: MealEntity?,
    foods: List<FoodEntity>,
    onDismiss: () -> Unit,
    onSave: (String, String, String, String, String, List<MealFoodItem>) -> Unit,
) {
    var label by remember { mutableStateOf(initial?.label ?: "") }
    var time by remember { mutableStateOf(initial?.time ?: "") }
    var calories by remember { mutableStateOf(initial?.calories?.toString() ?: "") }
    var desc by remember { mutableStateOf(initial?.description ?: "") }
    var foodQuery by remember { mutableStateOf("") }
    val items = remember { mutableStateListOf<MealFoodItem>().apply { addAll(Structured.decodeFoodItems(initial?.foodItemsJson)) } }

    val matches = remember(foods, foodQuery, items) {
        if (foodQuery.isBlank()) emptyList()
        else foods.filter { f ->
            (f.name.contains(foodQuery, true) || f.brand?.contains(foodQuery, true) == true) &&
                items.none { it.foodUid == f.uid }
        }.take(6)
    }
    val totals = remember(items.toList()) { Structured.totals(items) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(if (initial == null) "Add meal" else "Edit meal") },
        text = {
            Column(
                verticalArrangement = Arrangement.spacedBy(10.dp),
                modifier = Modifier.verticalScroll(rememberScrollState()),
            ) {
                PlainField("Label (e.g. Lunch)", label, { label = it })
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    PlainField("Time", time, { time = it }, Modifier.weight(1f))
                    if (items.isEmpty()) {
                        NumberField("kcal", calories, { calories = it }, Modifier.weight(1f), decimal = false)
                    }
                }

                Text("Foods", style = MaterialTheme.typography.labelLarge)
                items.forEachIndexed { i, it ->
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(it.name, modifier = Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium)
                        IconButton(onClick = {
                            val q = (it.quantity - 0.5).coerceAtLeast(0.5)
                            items[i] = it.copy(quantity = q)
                        }) { Icon(Icons.Filled.Remove, contentDescription = "Less") }
                        Text(trimNum(it.quantity), style = MaterialTheme.typography.bodyMedium)
                        IconButton(onClick = { items[i] = it.copy(quantity = it.quantity + 0.5) }) {
                            Icon(Icons.Filled.Add, contentDescription = "More")
                        }
                        IconButton(onClick = { items.removeAt(i) }) {
                            Icon(Icons.Filled.Delete, contentDescription = "Remove")
                        }
                    }
                }
                if (items.isNotEmpty()) {
                    Text(
                        "Total ${totals.calories.toInt()} kcal · P ${totals.proteinG.toInt()} · " +
                            "C ${totals.carbsG.toInt()} · F ${totals.fatG.toInt()}",
                        style = MaterialTheme.typography.bodySmall,
                    )
                }

                PlainField("Add food from library", foodQuery, { foodQuery = it })
                matches.forEach { f ->
                    Text(
                        f.name + (f.calories?.let { " · ${it.toInt()} kcal" } ?: ""),
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable {
                                items.add(
                                    MealFoodItem(
                                        foodUid = f.uid, name = f.name, quantity = 1.0,
                                        calories = f.calories, proteinG = f.proteinG,
                                        carbsG = f.carbsG, fatG = f.fatG,
                                    )
                                )
                                foodQuery = ""
                            }
                            .padding(vertical = 6.dp),
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }

                PlainField("Description", desc, { desc = it }, singleLine = false)
            }
        },
        confirmButton = {
            TextButton(
                onClick = { onSave(initial?.uid ?: "", label, time, calories, desc, items.toList()) },
                enabled = label.isNotBlank(),
            ) { Text("Save") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

/** "1.0" → "1", "1.5" → "1.5". */
private fun trimNum(v: Double): String =
    if (v == v.toLong().toDouble()) v.toLong().toString() else v.toString()

@Composable
private fun FoodsTab(vm: NutritionViewModel) {
    val foods by vm.foods.collectAsState(initial = emptyList())
    var query by remember { mutableStateOf("") }
    var showAdd by remember { mutableStateOf(false) }
    val filtered = remember(foods, query) {
        if (query.isBlank()) foods
        else foods.filter {
            it.name.contains(query, true) || (it.brand?.contains(query, true) == true)
        }
    }

    Box(Modifier.fillMaxSize()) {
        Column(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            PlainField("Search foods", query, { query = it })
            if (filtered.isEmpty()) {
                Text("No foods. Tap + to add one to your library.", style = MaterialTheme.typography.bodyMedium)
            } else {
                LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    items(filtered, key = { it.uid }) { f ->
                        Card(Modifier.fillMaxWidth()) {
                            Row(Modifier.fillMaxWidth().padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                                Column(Modifier.weight(1f)) {
                                    Text(f.name + (f.brand?.let { " · $it" } ?: ""), style = MaterialTheme.typography.titleMedium)
                                    val macros = listOfNotNull(
                                        f.calories?.let { "${it.toInt()} kcal" },
                                        f.proteinG?.let { "P ${it.toInt()}" },
                                        f.carbsG?.let { "C ${it.toInt()}" },
                                        f.fatG?.let { "F ${it.toInt()}" },
                                    )
                                    if (macros.isNotEmpty()) Text(macros.joinToString(" · "), style = MaterialTheme.typography.bodySmall)
                                }
                                IconButton(onClick = { vm.deleteFood(f.uid) }) {
                                    Icon(Icons.Filled.Delete, contentDescription = "Delete")
                                }
                            }
                        }
                    }
                }
            }
        }
        FloatingActionButton(
            onClick = { showAdd = true },
            modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp),
        ) { Icon(Icons.Filled.Add, contentDescription = "Add food") }
    }

    if (showAdd) {
        var name by remember { mutableStateOf("") }
        var brand by remember { mutableStateOf("") }
        var calories by remember { mutableStateOf("") }
        var protein by remember { mutableStateOf("") }
        var carbs by remember { mutableStateOf("") }
        var fat by remember { mutableStateOf("") }
        AlertDialog(
            onDismissRequest = { showAdd = false },
            title = { Text("Add food") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    PlainField("Name", name, { name = it })
                    PlainField("Brand", brand, { brand = it })
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        NumberField("kcal", calories, { calories = it }, Modifier.weight(1f))
                        NumberField("Protein", protein, { protein = it }, Modifier.weight(1f))
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        NumberField("Carbs", carbs, { carbs = it }, Modifier.weight(1f))
                        NumberField("Fat", fat, { fat = it }, Modifier.weight(1f))
                    }
                }
            },
            confirmButton = {
                TextButton(
                    onClick = { vm.addFood(name, brand, calories, protein, carbs, fat); showAdd = false },
                    enabled = name.isNotBlank(),
                ) { Text("Save") }
            },
            dismissButton = { TextButton(onClick = { showAdd = false }) { Text("Cancel") } },
        )
    }
}

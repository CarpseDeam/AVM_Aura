# gui/model_config_dialog.py
import logging
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QComboBox, QPushButton,
    QDialogButtonBox, QDoubleSpinBox, QFrame
)
from PySide6.QtCore import Qt
from core.llm_client import LLMClient

logger = logging.getLogger(__name__)


class ModelConfigurationDialog(QDialog):
    """A dialog for configuring LLM model assignments and temperatures for different roles."""

    def __init__(self, llm_client: LLMClient, parent=None):
        super().__init__(parent)
        self.llm_client = llm_client
        self.setWindowTitle("Configure AI Models")
        self.setMinimumWidth(500)

        self.roles = ["architect", "coder", "tester", "chat", "reviewer", "finalizer"]
        self.model_combos: dict[str, QComboBox] = {}
        self.temp_spins: dict[str, QDoubleSpinBox] = {}
        self.available_models = {}

        main_layout = QVBoxLayout(self)

        grid_layout = QGridLayout()
        grid_layout.setColumnStretch(1, 1)

        header_role = QLabel("<b>Role</b>")
        header_model = QLabel("<b>Assigned Model</b>")
        header_temp = QLabel("<b>Temperature</b>")
        grid_layout.addWidget(header_role, 0, 0)
        grid_layout.addWidget(header_model, 0, 1)
        grid_layout.addWidget(header_temp, 0, 2)

        for i, role in enumerate(self.roles, 1):
            role_label = QLabel(role.capitalize())
            model_combo = QComboBox()
            temp_spin = QDoubleSpinBox()
            temp_spin.setRange(0.0, 2.0)
            temp_spin.setSingleStep(0.05)
            temp_spin.setDecimals(2)

            self.model_combos[role] = model_combo
            self.temp_spins[role] = temp_spin

            grid_layout.addWidget(role_label, i, 0)
            grid_layout.addWidget(model_combo, i, 1)
            grid_layout.addWidget(temp_spin, i, 2)

        main_layout.addLayout(grid_layout)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)

    async def populate_models_async(self):
        """Fetches available models from the LLM client."""
        self.available_models = await self.llm_client.get_available_models()
        if not self.available_models:
            print("[ModelConfigurationDialog] Warning: No models were returned from the server.")

        for combo in self.model_combos.values():
            combo.clear()
            # Group by provider
            for provider, models in self.available_models.items():
                combo.addItem(f"--- {provider.upper()} ---")
                # The newly added item is at the last index. We get its model item and disable it.
                last_index = combo.count() - 1
                combo.model().item(last_index).setEnabled(False)

                for model_name in models:
                    combo.addItem(model_name, f"{provider}/{model_name}")

    def populate_settings(self):
        """Populates the dialog with current settings from the LLM client."""
        assignments = self.llm_client.get_role_assignments()
        temperatures = self.llm_client.get_role_temperatures()

        for role, combo in self.model_combos.items():
            assigned_key = assignments.get(role)
            if assigned_key:
                index = combo.findData(assigned_key)
                if index != -1:
                    combo.setCurrentIndex(index)

        for role, spin in self.temp_spins.items():
            temp = temperatures.get(role, 0.7)
            spin.setValue(temp)

    def accept(self):
        """Saves the new settings back to the LLM client."""
        new_assignments = {}
        for role, combo in self.model_combos.items():
            new_assignments[role] = combo.currentData()

        new_temps = {}
        for role, spin in self.temp_spins.items():
            new_temps[role] = spin.value()

        self.llm_client.set_role_assignments(new_assignments)
        self.llm_client.set_role_temperatures(new_temps)
        self.llm_client.save_assignments()
        logger.info("Saved new model configurations.")
        super().accept()
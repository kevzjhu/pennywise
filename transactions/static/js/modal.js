// --- Modal Dialog Controls ---
function openModal(mode, data = {}) {
    const modal = document.getElementById('transactionModal');
    const title = document.getElementById('modalTitle');
    const idField = document.getElementById('modal_transaction_id');
    const dateField = document.getElementById('id_date');
    const descField = document.getElementById('id_description');
    const amountField = document.getElementById('id_amount');
    const categoryField = document.getElementById('id_category');
    const notesField = document.getElementById('id_notes');

    if (mode === 'edit') {
        title.innerText = 'Edit Transaction';
        idField.value = data.id || '';
        dateField.value = data.date || '';
        descField.value = data.description || '';
        amountField.value = data.amount || '';
        categoryField.value = data.category || '';
        notesField.value = data.notes || '';
    } else {
        title.innerText = 'Log New Transaction';
        idField.value = '';
        dateField.value = new Date().toISOString().split('T')[0];
        descField.value = '';
        amountField.value = '';
        notesField.value = '';
        if (categoryField && categoryField.options.length > 0) {
            categoryField.selectedIndex = 0;
        }
    }
    if (modal) modal.classList.remove('hidden');
    updateCharCount();
}

function closeModal() {
    const modal = document.getElementById('transactionModal');
    if (modal) modal.classList.add('hidden');
}

// Character Limit Counter
function updateCharCount() {
    const notesField = document.getElementById('id_notes');
    const charCount = document.getElementById('charCount');
    if (notesField && charCount) {
        charCount.innerText = `${notesField.value.length}/200`;
    }
}

// --- Excel-Style Dropdown Filter Menus ---
function toggleExcelDropdown(event, menuId) {
    event.stopPropagation();
    event.preventDefault();

    const menus = ['dateMenu', 'descMenu', 'catMenu', 'amtMenu'];
    menus.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            if (id === menuId) {
                el.classList.toggle('hidden');
            } else {
                el.classList.add('hidden');
            }
        }
    });
}

function closeAllDropdowns() {
    ['dateMenu', 'descMenu', 'catMenu', 'amtMenu'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.classList.add('hidden');
    });
}

// --- Range Constraints and Validation ---
function syncAmountConstraints() {
    const minInput = document.getElementById('filter_min_amount');
    const maxInput = document.getElementById('filter_max_amount');

    if (minInput && maxInput) {
        // HTML5 Validation constraint: dynamically sets max input's absolute floor limit
        if (minInput.value) {
            maxInput.min = minInput.value;
        } else {
            maxInput.removeAttribute('min');
        }
    }
}

function validateAmountRange(formElement) {
    const minVal = parseFloat(document.getElementById('filter_min_amount').value);
    const maxVal = parseFloat(document.getElementById('filter_max_amount').value);

    // Hard gate blocking form validation if constraints fail
    if (!isNaN(minVal) && !isNaN(maxVal) && maxVal < minVal) {
        alert("Maximum value constraint error: Maximum amount cannot be lower than the minimum amount value.");
        return false;
    }
    closeAllDropdowns();
    return true;
}

// --- Global Click Router Handling Outside Elements ---
document.addEventListener('click', function (event) {
    const isInsideDropdown = event.target.closest('#dateMenu, #descMenu, #catMenu, #amtMenu');
    const isControlFunnel = event.target.closest('button[onclick*="toggleExcelDropdown"]');
    const isFormInput = event.target.tagName === 'INPUT' || event.target.tagName === 'SELECT' || event.target.tagName === 'OPTION';

    if (!isInsideDropdown && !isControlFunnel && !isFormInput) {
        closeAllDropdowns();
    }
});

// Setup Initial Bounds Checks
document.addEventListener('DOMContentLoaded', function () {
    syncAmountConstraints();
});

// Re-hook listeners following HTMX asynchronous partial replacements
document.addEventListener('htmx:afterSwap', function (evt) {
    if (evt.detail.target.id === "table-container") {
        syncAmountConstraints();
    }
});
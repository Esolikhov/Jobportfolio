// Функция для переключения всех чекбоксов
document.getElementById('toggle-all').addEventListener('click', function() {
    const checkboxes = document.querySelectorAll('.document-table input[type="checkbox"]');
    const isChecked = checkboxes[0].checked;
    checkboxes.forEach(checkbox => {
        if (!checkbox.disabled) {
            checkbox.checked = !isChecked;
        }
    });
});

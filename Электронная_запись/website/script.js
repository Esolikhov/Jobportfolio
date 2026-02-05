let selectedTime = null;

document.addEventListener('DOMContentLoaded', function() {
    setTimeout(function() {
        document.getElementById('mainContent').style.display = 'block';
    }, 3000);
    
    setMinDate();
    loadDoctors();
    setupEventListeners();
});

function setMinDate() {
    const dateInput = document.getElementById('date');
    const today = new Date().toISOString().split('T')[0];
    dateInput.min = today;
}

function setupEventListeners() {
    document.getElementById('doctor').addEventListener('change', loadTimeSlots);
    document.getElementById('date').addEventListener('change', loadTimeSlots);
    
    document.getElementById('phone').addEventListener('input', function(e) {
        let value = e.target.value.replace(/\D/g, '');
        
        if (value.length > 0 && !value.startsWith('992')) {
            value = '992' + value;
        }
        if (value.length > 12) {
            value = value.slice(0, 12);
        }
        
        let formatted = '';
        if (value.length > 0) {
            formatted = '+' + value.slice(0, 3);
            if (value.length > 3) formatted += ' ' + value.slice(3, 5);
            if (value.length > 5) formatted += ' ' + value.slice(5, 8);
            if (value.length > 8) formatted += ' ' + value.slice(8, 12);
        }
        
        e.target.value = formatted;
    });
}

function loadDoctors() {
    fetch('/api/doctors')
        .then(response => response.json())
        .then(doctors => {
            const select = document.getElementById('doctor');
            doctors.forEach(doctor => {
                const option = document.createElement('option');
                option.value = doctor.id;
                option.textContent = `${doctor.name} — ${doctor.specialization}`;
                select.appendChild(option);
            });
        })
        .catch(error => {
            console.error('Ошибка загрузки врачей:', error);
        });
}

function loadTimeSlots() {
    const doctorId = document.getElementById('doctor').value;
    const date = document.getElementById('date').value;
    const container = document.getElementById('timeSlots');
    
    if (!doctorId || !date) {
        container.innerHTML = '<p class="hint">Выберите врача и дату</p>';
        return;
    }
    
    container.innerHTML = '<p class="hint">Загрузка...</p>';
    selectedTime = null;
    
    fetch(`/api/available-slots?doctor_id=${doctorId}&date=${date}`)
        .then(response => response.json())
        .then(slots => {
            container.innerHTML = '';
            
            const today = new Date().toISOString().split('T')[0];
            const isToday = date === today;
            const currentHour = new Date().getHours();
            const currentMinute = new Date().getMinutes();
            
            slots.forEach(slot => {
                const div = document.createElement('div');
                const [slotHour, slotMinute] = slot.time.split(':').map(Number);
                
                let isPast = false;
                if (isToday) {
                    if (slotHour < currentHour || (slotHour === currentHour && slotMinute <= currentMinute)) {
                        isPast = true;
                    }
                }
                
                const isAvailable = slot.available && !isPast;
                div.className = isAvailable ? 'time-slot' : 'time-slot disabled';
                div.textContent = slot.time;
                div.dataset.time = slot.time;
                
                if (isAvailable) {
                    div.addEventListener('click', function() {
                        document.querySelectorAll('.time-slot').forEach(s => {
                            s.classList.remove('selected');
                        });
                        this.classList.add('selected');
                        selectedTime = this.dataset.time;
                    });
                }
                
                container.appendChild(div);
            });
        })
        .catch(error => {
            console.error('Ошибка загрузки слотов:', error);
            container.innerHTML = '<p class="hint">Ошибка загрузки</p>';
        });
}

function submitBooking() {
    const name = document.getElementById('patientName').value.trim();
    const phone = document.getElementById('phone').value.trim();
    const doctorId = document.getElementById('doctor').value;
    const serviceName = document.getElementById('service').value.trim();
    const date = document.getElementById('date').value;
    
    if (!name) {
        alert('Введите ваше имя');
        document.getElementById('patientName').focus();
        return;
    }
    
    if (!phone || phone.length < 10) {
        alert('Введите корректный номер телефона');
        document.getElementById('phone').focus();
        return;
    }
    
    if (!doctorId) {
        alert('Выберите врача');
        document.getElementById('doctor').focus();
        return;
    }
    
    if (!date) {
        alert('Выберите дату');
        document.getElementById('date').focus();
        return;
    }
    
    if (!selectedTime) {
        alert('Выберите время приёма');
        return;
    }
    
    const doctorSelect = document.getElementById('doctor');
    const doctorName = doctorSelect.options[doctorSelect.selectedIndex].text;
    
    const data = {
        patient_name: name,
        phone: phone,
        doctor_id: parseInt(doctorId),
        appointment_date: date,
        appointment_time: selectedTime,
        service_name: serviceName || null
    };
    
    fetch('/api/appointments', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(result => {
        if (result.success || result.id) {
            showConfirmation(data, doctorName);
        } else {
            alert('Ошибка при записи. Попробуйте снова.');
        }
    })
    .catch(error => {
        console.error('Ошибка:', error);
        alert('Ошибка при записи. Попробуйте снова.');
    });
}

function showConfirmation(data, doctorName) {
    document.getElementById('bookingForm').style.display = 'none';
    document.getElementById('confirmation').style.display = 'block';
    
    const dateObj = new Date(data.appointment_date);
    const options = { day: 'numeric', month: 'long', year: 'numeric' };
    const formattedDate = dateObj.toLocaleDateString('ru-RU', options);
    
    document.getElementById('confirmDetails').innerHTML = `
        <p><strong>Врач:</strong> ${doctorName}</p>
        ${data.service_name ? `<p><strong>Услуга:</strong> ${data.service_name}</p>` : ''}
        <p><strong>Дата:</strong> ${formattedDate}</p>
        <p><strong>Время:</strong> ${data.appointment_time}</p>
        <p><strong>Пациент:</strong> ${data.patient_name}</p>
        <p><strong>Телефон:</strong> ${data.phone}</p>
    `;
}

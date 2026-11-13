document.addEventListener('DOMContentLoaded', function () {
    const passwordInput = document.querySelector('#password');
    const confirmInput = document.querySelector('#confirm_password');
    const strengthBar = document.querySelector('#passwordStrengthBar');

    if (passwordInput) {
        passwordInput.addEventListener('input', function () {
            const value = passwordInput.value;
            let score = 0;
            if (value.length >= 8) score += 1;
            if (/[A-Z]/.test(value)) score += 1;
            if (/[a-z]/.test(value)) score += 1;
            if (/\d/.test(value)) score += 1;
            if (/[^A-Za-z0-9]/.test(value)) score += 1;

            const percent = Math.min((score / 5) * 100, 100);
            strengthBar.style.width = percent + '%';
            if (percent < 40) {
                strengthBar.style.backgroundColor = '#d93649';
            } else if (percent < 70) {
                strengthBar.style.backgroundColor = '#f59e0b';
            } else {
                strengthBar.style.backgroundColor = '#14a44d';
            }
        });
    }

    if (confirmInput) {
        confirmInput.addEventListener('input', function () {
            const password = passwordInput ? passwordInput.value : '';
            const confirm = confirmInput.value;
            if (password && confirm && password !== confirm) {
                confirmInput.setCustomValidity('Passwords do not match');
            } else {
                confirmInput.setCustomValidity('');
            }
        });
    }
});

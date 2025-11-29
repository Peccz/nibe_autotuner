// Nibe Autotuner Mobile App - Main JavaScript

// PWA Install Prompt
let deferredPrompt;

window.addEventListener('beforeinstallprompt', (e) => {
    // Prevent the mini-infobar from appearing on mobile
    e.preventDefault();
    // Stash the event so it can be triggered later
    deferredPrompt = e;
    // Show install prompt
    showInstallPrompt();
});

function showInstallPrompt() {
    const promptElement = document.getElementById('installPrompt');
    if (promptElement) {
        promptElement.style.display = 'block';
    }
}

function hideInstallPrompt() {
    const promptElement = document.getElementById('installPrompt');
    if (promptElement) {
        promptElement.style.display = 'none';
    }
}

// Install button click
document.addEventListener('DOMContentLoaded', () => {
    const installBtn = document.getElementById('installBtn');
    const dismissBtn = document.getElementById('dismissBtn');

    if (installBtn) {
        installBtn.addEventListener('click', async () => {
            if (!deferredPrompt) {
                return;
            }

            // Show the install prompt
            deferredPrompt.prompt();

            // Wait for the user to respond to the prompt
            const { outcome } = await deferredPrompt.userChoice;

            if (outcome === 'accepted') {
                console.log('User accepted the install prompt');
            } else {
                console.log('User dismissed the install prompt');
            }

            // Clear the deferredPrompt
            deferredPrompt = null;
            hideInstallPrompt();
        });
    }

    if (dismissBtn) {
        dismissBtn.addEventListener('click', () => {
            hideInstallPrompt();
            // Don't show again for 7 days
            localStorage.setItem('installPromptDismissed', Date.now());
        });
    }

    // Check if already dismissed recently
    const dismissed = localStorage.getItem('installPromptDismissed');
    if (dismissed) {
        const daysSinceDismiss = (Date.now() - parseInt(dismissed)) / (1000 * 60 * 60 * 24);
        if (daysSinceDismiss < 7) {
            hideInstallPrompt();
        }
    }
});

// Check if installed
window.addEventListener('appinstalled', () => {
    console.log('PWA was installed');
    hideInstallPrompt();
});

// Utility Functions
function formatDateTime(isoString) {
    const date = new Date(isoString);
    return date.toLocaleString('sv-SE', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    });
}

function formatDate(isoString) {
    const date = new Date(isoString);
    return date.toLocaleDateString('sv-SE');
}

function formatTime(isoString) {
    const date = new Date(isoString);
    return date.toLocaleTimeString('sv-SE', { hour: '2-digit', minute: '2-digit' });
}

// Toast notifications
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    toast.style.cssText = `
        position: fixed;
        top: 70px;
        left: 50%;
        transform: translateX(-50%);
        background: ${type === 'error' ? '#f44336' : type === 'success' ? '#4caf50' : '#2196f3'};
        color: white;
        padding: 12px 24px;
        border-radius: 8px;
        z-index: 1000;
        animation: slideDown 0.3s;
    `;

    document.body.appendChild(toast);

    setTimeout(() => {
        toast.style.animation = 'slideUp 0.3s';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// Handle network status
window.addEventListener('online', () => {
    showToast('Ansluten till internet', 'success');
});

window.addEventListener('offline', () => {
    showToast('Ingen internetanslutning', 'error');
});

// Prevent pull-to-refresh on iOS
let touchStartY = 0;
document.addEventListener('touchstart', (e) => {
    touchStartY = e.touches[0].clientY;
}, { passive: true });

document.addEventListener('touchmove', (e) => {
    const touchY = e.touches[0].clientY;
    const touchDiff = touchY - touchStartY;

    // If scrolling down and at top of page, prevent default
    if (touchDiff > 0 && window.scrollY === 0) {
        e.preventDefault();
    }
}, { passive: false });

/**
 * Global application actions (Reload ABS, Delete Torrent, Send Torrent, Open External)
 */

function showNotification(message, type = 'info') {
    // Create a notification container if it doesn't exist
    let container = document.getElementById('notification-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'notification-container';
        container.style.position = 'fixed';
        container.style.top = '20px';
        container.style.left = '50%';
        container.style.transform = 'translateX(-50%)';
        container.style.zIndex = '10000';
        container.style.display = 'flex';
        container.style.flexDirection = 'column';
        container.style.gap = '10px';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.style.padding = '12px 24px';
    toast.style.borderRadius = '5px';
    toast.style.color = '#fff';
    toast.style.fontSize = '1rem';
    toast.style.boxShadow = '0 4px 6px rgba(0,0,0,0.2)';
    toast.style.opacity = '0';
    toast.style.transition = 'opacity 0.3s ease';

    // Color based on type
    if (type === 'error') {
        toast.style.backgroundColor = '#d32f2f'; // Red
    } else {
        toast.style.backgroundColor = '#43a047'; // Green
    }

    toast.textContent = message;
    container.appendChild(toast);

    // Fade in
    requestAnimationFrame(() => {
        toast.style.opacity = '1';
    });

    // Remove after 3 seconds
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.addEventListener('transitionend', () => {
            toast.remove();
        });
    }, 3000);
}

function reloadLibrary() {
    if (!confirm("Are you sure you want to initiate a library scan?")) {
        return;
    }

    const csrfMeta = document.querySelector('meta[name="csrf-token"]');
    const csrfToken = csrfMeta ? csrfMeta.getAttribute('content') : '';

    fetch("/reload_library", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": csrfToken
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.message.toLowerCase().includes("failed")) {
             showNotification(data.message, 'error');
        } else {
             showNotification(data.message, 'success');
        }
    })
    .catch(error => {
        console.error("Error:", error);
        showNotification("An error occurred while trying to reload the library.", 'error');
    });
}

function deleteTorrent(torrentId) {
    if (!confirm("Are you sure you want to remove this torrent? The downloaded files will NOT be deleted.")) {
        return;
    }

    const csrfMeta = document.querySelector('meta[name="csrf-token"]');
    const csrfToken = csrfMeta ? csrfMeta.getAttribute('content') : '';

    fetch("/delete", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": csrfToken
        },
        body: JSON.stringify({ id: torrentId }),
    })
    .then(response => response.json())
    .then(data => {
        showNotification(data.message, 'success');
        if (data.message.includes("successfully")) {
            // Delay reload slightly to let user see the toast
            setTimeout(() => location.reload(), 1000);
        }
    })
    .catch(error => {
        console.error("Error:", error);
        showNotification("An error occurred while removing the torrent.", 'error');
    });
}

function sendTorrent(link, title, buttonElement) {
  const csrfMeta = document.querySelector('meta[name="csrf-token"]');
  if (!csrfMeta) {
      showNotification("Security Error: CSRF token missing. Please refresh the page.", 'error');
      return;
  }
  const csrfToken = csrfMeta.getAttribute('content');

  // Disable specific button to prevent double-clicks
  let originalBtnText = "";
  if (buttonElement) {
      buttonElement.disabled = true;
      originalBtnText = buttonElement.innerText;
      buttonElement.innerText = "Sending...";
  }

  fetch("/send", {
    method: "POST",
    headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken
    },
    body: JSON.stringify({ link: link, title: title }),
  })
    .then((response) => {
      if (!response.ok) {
        return response.json().then(err => {
            throw new Error(err.message || 'Server Error');
        }).catch(() => {
            throw new Error(`Request failed with status ${response.status}`);
        });
      }
      return response.json();
    })
    .then((data) => {
      showNotification(data.message, 'success');
    })
    .catch((error) => {
      console.error('Download failed:', error);
      showNotification("Failed to send download: " + error.message, 'error');
    })
    .finally(() => {
      if (buttonElement) {
          buttonElement.disabled = false;
          buttonElement.innerText = originalBtnText;
      }
    });
}

function openExternalLink(url) {
    const warningMessage = "SECURITY WARNING:\n\n" +
        "You are about to open this link directly in your browser.\n" +
        "This traffic will NOT be routed through the server's VPN connection.\n\n" +
        "Your real IP address may be exposed to the target website.\n\n" +
        "Are you sure you want to proceed?";

    if (confirm(warningMessage)) {
        window.open(url, '_blank');
    }
}

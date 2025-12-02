/**
 * Global application actions (Reload ABS, Delete Torrent)
 */

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
        alert(data.message);
    })
    .catch(error => {
        console.error("Error:", error);
        alert("An error occurred while trying to reload the library.");
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
        alert(data.message);
        if (data.message.includes("successfully")) {
            location.reload();
        }
    })
    .catch(error => {
        console.error("Error:", error);
        alert("An error occurred while removing the torrent.");
    });
}

// Handles spoiler-blind reveal behavior for redacted member fields.
// - Buttons with class .spoiler-blind-btn and data-field/data-member-id
// - When clicked, toggles the corresponding element with id="<field>-<memberId>"
// - If the element is revealed and Bootstrap modal config exists, a modal is shown on member view load for rostermeisters

document.addEventListener('DOMContentLoaded', function () {
    function revealField(memberId, field) {
        var containerId = field + '-' + memberId;
        var el = document.getElementById(containerId);
        if (!el) return false;
        el.classList.remove('d-none');
        el.classList.add('revealed');
        return true;
    }

    document.querySelectorAll('.spoiler-blind-btn').forEach(function (btn) {
        btn.addEventListener('click', function (e) {
            e.preventDefault();
            var field = btn.getAttribute('data-field');
            var memberId = btn.getAttribute('data-member-id');
            var revealed = revealField(memberId, field);
            if (revealed) {
                // replace the button text to indicate revealed
                btn.textContent = 'Revealed';
                btn.disabled = true;
            } else {
                // fallback: navigate to the member view (href not provided) - do nothing
            }
        });
    });

    // On member view pages, show modal to rostermeisters if element with id 'redaction-alert-modal' exists
    var modalEl = document.getElementById('redaction-alert-modal');
    if (modalEl) {
        try {
            var modal = new bootstrap.Modal(modalEl);
            modal.show();
        } catch (err) {
            // Bootstrap not available; do nothing
        }
    }
});

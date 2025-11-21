/**
 * CMS Formset Management JavaScript
 * Shared functionality for managing Django formsets in CMS templates
 */

function initializeFormsetManagement() {
    const totalForms = document.querySelector('#id_documents-TOTAL_FORMS');
    const addButton = document.querySelector('#add-document');

    if (!addButton || !totalForms) return;

    addButton.addEventListener('click', function (e) {
        e.preventDefault();
        addNewFormsetForm();
    });
}

function addNewFormsetForm() {
    const formsetContainer = document.querySelector('#document-formset');
    const totalForms = document.querySelector('#id_documents-TOTAL_FORMS');
    const formCount = parseInt(totalForms.value);

    // Create new form HTML
    const newFormHTML = `
        <div class="document-form border rounded p-3 mb-3" style="background: #f8f9fa;">
            <div class="row">
                <div class="col-md-8">
                    <label class="form-label fw-bold">
                        <i class="bi bi-cloud-upload text-primary me-2"></i>File
                    </label>
                    <input type="file" name="documents-${formCount}-file" class="form-control file-drop-area" id="id_documents-${formCount}-file">
                </div>
                <div class="col-md-4">
                    <label class="form-label fw-bold">
                        <i class="bi bi-tag text-primary me-2"></i>Title (Optional)
                    </label>
                    <input type="text" name="documents-${formCount}-title" class="form-control" id="id_documents-${formCount}-title" placeholder="Optional: Enter a title for this file">
                </div>
            </div>
            <input type="hidden" name="documents-${formCount}-id" id="id_documents-${formCount}-id">
            <div class="mt-2">
                <button type="button" class="btn btn-sm btn-outline-danger remove-form" onclick="removeFormsetForm(this)">
                    <i class="bi bi-trash"></i> Remove
                </button>
            </div>
        </div>
    `;

    // Add new form to container
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = newFormHTML;
    const newForm = tempDiv.firstElementChild;

    formsetContainer.appendChild(newForm);

    // Update total forms count
    totalForms.value = formCount + 1;

    // Initialize drag-and-drop for new file input
    initializeDragAndDropForElement(newForm.querySelector('.file-drop-area'));
}

function removeFormsetForm(button) {
    const form = button.closest('.document-form');
    const totalForms = document.querySelector('#id_documents-TOTAL_FORMS');
    form.remove();

    // Update total forms count
    const currentCount = parseInt(totalForms.value);
    totalForms.value = Math.max(0, currentCount - 1);
}

function initializeDragAndDrop() {
    document.querySelectorAll('input[type="file"]').forEach(initializeDragAndDropForElement);
}

function initializeDragAndDropForElement(fileInput) {
    if (!fileInput) return;

    const dropArea = fileInput.parentElement;

    // Add drag-and-drop styling
    fileInput.style.position = 'relative';
    fileInput.style.zIndex = '2';

    // Create overlay for drag-and-drop feedback
    const overlay = document.createElement('div');
    overlay.className = 'drag-drop-overlay';
    overlay.style.cssText = `
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        border: 2px dashed #007bff;
        background: rgba(0, 123, 255, 0.1);
        display: none;
        align-items: center;
        justify-content: center;
        font-weight: bold;
        color: #007bff;
        border-radius: 8px;
        z-index: 1;
    `;
    overlay.textContent = '📁 Drop file here';
    dropArea.style.position = 'relative';
    dropArea.appendChild(overlay);

    // Prevent default drag behaviors
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropArea.addEventListener(eventName, preventDefaults, false);
        document.body.addEventListener(eventName, preventDefaults, false);
    });

    // Highlight drop area when item is dragged over it
    ['dragenter', 'dragover'].forEach(eventName => {
        dropArea.addEventListener(eventName, () => {
            overlay.style.display = 'flex';
        }, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropArea.addEventListener(eventName, () => {
            overlay.style.display = 'none';
        }, false);
    });

    // Handle dropped files
    dropArea.addEventListener('drop', handleDrop, false);

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    function handleDrop(e) {
        const dt = e.dataTransfer;
        const files = dt.files;

        if (files.length > 0) {
            fileInput.files = files;

            // Update visual feedback
            const fileName = files[0].name;
            const feedback = document.createElement('div');
            feedback.className = 'mt-2 text-success small';
            feedback.innerHTML = `<i class="bi bi-check-circle me-1"></i>Selected: ${fileName}`;

            // Remove any existing feedback
            const existingFeedback = dropArea.querySelector('.mt-2.text-success');
            if (existingFeedback) {
                existingFeedback.remove();
            }

            dropArea.appendChild(feedback);
        }
    }
}

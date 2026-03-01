/**
 * Kiosk Device Fingerprinting Module
 *
 * Collects browser and device characteristics for fingerprinting kiosk devices.
 * Used by both bind_device.html and verify_device.html templates.
 */

/**
 * Collect browser and device fingerprint data
 * @returns {Promise<string>} Fingerprint string with components separated by '|||'
 */
async function collectFingerprint() {
    const components = [];

    // User Agent
    components.push(navigator.userAgent);

    // Screen properties
    components.push(screen.width + 'x' + screen.height);
    components.push(screen.colorDepth);
    components.push(window.devicePixelRatio || 1);

    // Timezone
    components.push(Intl.DateTimeFormat().resolvedOptions().timeZone);
    components.push(new Date().getTimezoneOffset());

    // Platform
    components.push(navigator.platform);
    components.push(navigator.language);
    components.push(navigator.languages ? navigator.languages.join(',') : '');

    // Hardware concurrency (CPU cores)
    components.push(navigator.hardwareConcurrency || 'unknown');

    // Device memory (if available)
    components.push(navigator.deviceMemory || 'unknown');

    // Canvas fingerprint
    try {
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');
        canvas.width = 200;
        canvas.height = 50;

        // Draw text with various properties
        ctx.textBaseline = 'top';
        ctx.font = '14px Arial';
        ctx.fillStyle = '#f60';
        ctx.fillRect(125, 1, 62, 20);
        ctx.fillStyle = '#069';
        ctx.fillText('Manage2Soar Kiosk', 2, 15);
        ctx.fillStyle = 'rgba(102, 204, 0, 0.7)';
        ctx.fillText('Fingerprint', 4, 35);

        components.push(canvas.toDataURL());
    } catch (e) {
        components.push('canvas-error');
    }

    // WebGL fingerprint
    try {
        const canvas = document.createElement('canvas');
        const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
        if (gl) {
            const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
            if (debugInfo) {
                components.push(gl.getParameter(debugInfo.UNMASKED_VENDOR_WEBGL));
                components.push(gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL));
            }
            components.push(gl.getParameter(gl.VERSION));
        }
    } catch (e) {
        components.push('webgl-error');
    }

    // Audio context fingerprint
    let audioContext = null;
    let oscillator = null;
    let oscillatorStarted = false;
    try {
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
        oscillator = audioContext.createOscillator();
        const analyser = audioContext.createAnalyser();
        const gainNode = audioContext.createGain();
        const scriptProcessor = audioContext.createScriptProcessor(4096, 1, 1);

        gainNode.gain.value = 0; // Mute
        oscillator.type = 'triangle';
        oscillator.connect(analyser);
        analyser.connect(scriptProcessor);
        scriptProcessor.connect(gainNode);
        gainNode.connect(audioContext.destination);

        // Set flag BEFORE start() to ensure cleanup works even if start() fails
        oscillatorStarted = true;
        oscillator.start(0);

        // Wait briefly for audio context to stabilize before capturing sample rate
        // This ensures consistent fingerprinting across different browsers/devices
        await new Promise(resolve => setTimeout(resolve, 10));

        components.push(audioContext.sampleRate);
    } catch (e) {
        components.push('audio-error');
    } finally {
        // Ensure cleanup even if error occurs
        try {
            if (oscillator && oscillatorStarted) oscillator.stop();
            if (audioContext && audioContext.state !== 'closed') audioContext.close();
        } catch (cleanupError) {
            // Ignore cleanup errors
        }
    }

    // Combine all components into a single string
    const fingerprintString = components.join('|||');

    return fingerprintString;
}

/**
 * Get the masked CSRF token required by Django 5.x's X-CSRFToken header.
 *
 * The raw csrftoken cookie holds a 32-char unmasked secret; Django 5.x
 * requires the 64-char masked form token, so reading the cookie directly
 * always produces a 403.  Reads the DOM hidden input rendered by
 * {% csrf_token %} instead, which carries the correctly masked value.
 *
 * The templates that load this script (bind_device.html, verify_device.html)
 * include a hidden #csrf-anchor form so this DOM query is always available.
 *
 * @returns {string} The masked CSRF token, or empty string if not found.
 */
function getCsrfToken() {
    const domInput = document.querySelector('[name=csrfmiddlewaretoken]');
    return domInput ? domInput.value : '';
}

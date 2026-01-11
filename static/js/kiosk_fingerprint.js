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
            if (oscillator) oscillator.stop();
            if (audioContext) audioContext.close();
        } catch (cleanupError) {
            // Ignore cleanup errors
        }
    }

    // Combine all components into a single string
    const fingerprintString = components.join('|||');

    return fingerprintString;
}

/**
 * Get CSRF token from cookie
 * @returns {string|null} CSRF token value
 */
function getCsrfToken() {
    const name = 'csrftoken';
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

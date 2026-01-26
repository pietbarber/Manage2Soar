/**
 * Banner Brightness Detection for Auto-Contrast Text
 * Issue #547: Site Style Enhancements
 *
 * Analyzes banner image brightness to determine whether light or dark text
 * should be used for optimal contrast.
 */

/**
 * Brightness threshold for determining text color (0-255 scale)
 * Values above this threshold are considered "bright" and get dark text
 * Values below get light text
 */
const BRIGHTNESS_THRESHOLD = 140;

/**
 * Analyzes image brightness and applies appropriate text color class
 * @param {string} imageUrl - URL of the banner image
 * @param {string} bannerId - ID of the banner element
 */
function detectBannerBrightness(imageUrl, bannerId) {
    const banner = document.getElementById(bannerId);
    if (!banner) return;

    const img = new Image();

    // Only set crossOrigin for truly cross-origin URLs to avoid CORS issues
    try {
        const pageOrigin = window.location.origin;
        const imgUrl = new URL(imageUrl, pageOrigin);
        if (imgUrl.origin !== pageOrigin) {
            img.crossOrigin = 'Anonymous';
        }
    } catch (e) {
        // If URL parsing fails, skip setting crossOrigin
        console.warn('Banner brightness detection: Unable to parse image URL', e);
    }

    img.onload = function () {
        try {
            // Sample center region of image (avoid edges which may be darker/lighter)
            // Note: This samples a 100x100 center region for performance. For images with
            // non-uniform brightness, consider future enhancements:
            // - Sample the specific region where text overlay appears
            // - Sample multiple regions and use weighted averages
            // - Add manual override option in CMS admin for edge cases
            const sampleWidth = Math.min(100, img.width);
            const sampleHeight = Math.min(100, img.height);
            const sampleX = (img.width - sampleWidth) / 2;
            const sampleY = (img.height - sampleHeight) / 2;

            const canvas = document.createElement('canvas');
            const ctx = canvas.getContext('2d');

            // Only create a canvas as large as the sampled region (performance optimization)
            canvas.width = sampleWidth;
            canvas.height = sampleHeight;

            // Draw only the sampled region into the smaller canvas
            ctx.drawImage(
                img,
                sampleX,
                sampleY,
                sampleWidth,
                sampleHeight,
                0,
                0,
                sampleWidth,
                sampleHeight
            );

            const imageData = ctx.getImageData(0, 0, sampleWidth, sampleHeight);
            const data = imageData.data;

            // Calculate average brightness
            let totalBrightness = 0;
            for (let i = 0; i < data.length; i += 4) {
                const r = data[i];
                const g = data[i + 1];
                const b = data[i + 2];
                // Weighted brightness calculation (human eye perceives green as brighter)
                const brightness = (0.299 * r + 0.587 * g + 0.114 * b);
                totalBrightness += brightness;
            }
            const avgBrightness = totalBrightness / (data.length / 4);

            // Apply appropriate text color class based on brightness threshold
            if (avgBrightness > BRIGHTNESS_THRESHOLD) {
                banner.classList.add('dark-text');
                banner.classList.remove('light-text');
            } else {
                banner.classList.add('light-text');
                banner.classList.remove('dark-text');
            }
        } catch (error) {
            console.warn('Banner brightness detection failed, using default light text:', error);
            banner.classList.add('light-text');
        }
    };

    img.onerror = function () {
        console.warn('Banner image failed to load, using default light text');
        banner.classList.add('light-text');
    };

    img.src = imageUrl;
}

/**
 * Initialize parallax scrolling effect for banner images
 * Issue #570: Uses transform instead of background-attachment: fixed
 * to avoid image cropping issues while maintaining parallax effect.
 *
 * @param {string} bannerId - ID of the banner element
 */
function initBannerParallax(bannerId) {
    const banner = document.getElementById(bannerId);
    if (!banner) return;

    const bannerImage = banner.querySelector('.page-banner-image');
    if (!bannerImage) return;

    // Check for reduced motion preference
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        return; // Skip parallax for users who prefer reduced motion
    }

    // Parallax speed factor (0.3 = image moves at 30% of scroll speed)
    const parallaxSpeed = 0.3;

    function updateParallax() {
        const scrollY = window.scrollY;
        const bannerRect = banner.getBoundingClientRect();

        // Only apply parallax when banner is visible
        if (bannerRect.bottom > 0 && bannerRect.top < window.innerHeight) {
            const offset = scrollY * parallaxSpeed;
            bannerImage.style.transform = `translateY(${offset}px)`;
        }
    }

    // Use requestAnimationFrame for smooth scrolling
    let ticking = false;
    window.addEventListener('scroll', function() {
        if (!ticking) {
            window.requestAnimationFrame(function() {
                updateParallax();
                ticking = false;
            });
            ticking = true;
        }
    }, { passive: true });

    // Initial position
    updateParallax();
}

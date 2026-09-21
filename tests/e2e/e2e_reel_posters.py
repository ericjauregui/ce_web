from tests.e2e.common import BaseE2ETest


class ReelPosterRaceE2ETests(BaseE2ETest):
    viewport = {"width": 390, "height": 844}

    def test_late_poster_cannot_replace_started_video(self):
        # Keep real image/video decoding, but control the poster completion order.
        self.page.add_init_script("""
          window.pendingReelPosters = [];
          window.latePosterWrites = [];
          const NativeImage = window.Image;
          window.Image = function (...args) {
            const image = new NativeImage(...args);
            Object.defineProperty(image, 'onload', {set(callback) {
              image.addEventListener('load', event => {
                if (image.src.includes('/reels/posters/')) {
                  window.pendingReelPosters.push(() => callback.call(image, event));
                } else callback.call(image, event);
              });
            }});
            return image;
          };
          const poster = Object.getOwnPropertyDescriptor(HTMLVideoElement.prototype, 'poster');
          Object.defineProperty(HTMLVideoElement.prototype, 'poster', {
            ...poster, set(value) {
              if (this.hasAttribute('src')) window.latePosterWrites.push(value);
              poster.set.call(this, value);
            }
          });
        """)
        self.goto("/")
        self.page.locator("#latestVideosTrack").scroll_into_view_if_needed()
        self.page.wait_for_function("""() => {
          const video = document.querySelector('.inline-reel-card.is-active video');
          return video && video.readyState >= 2 && video.currentTime > 0.1
            && window.pendingReelPosters.length > 0;
        }""", timeout=15000, polling=100)
        self.assertTrue(self.page.locator(".inline-reel-card.is-active").evaluate(
            "card => card.classList.contains('is-loaded')"))
        # A paused video must retain its current frame, too.
        self.page.locator(".inline-reel-card.is-active video").evaluate("video => video.pause()")
        self.page.evaluate("window.pendingReelPosters.splice(0).forEach(complete => complete())")
        self.assertEqual(self.page.evaluate("window.latePosterWrites"), [])
        self.assertGreater(self.page.locator(".inline-reel-card:not(.is-active) video[poster]").count(), 0)
        self.assertTrue(self.page.locator(".inline-reel-card.is-active video").evaluate("""
          async video => {
            await video.play();
            if (!video.requestVideoFrameCallback) return video.readyState >= 2;
            return new Promise(resolve => {
              const timer = setTimeout(() => resolve(false), 5000);
              video.requestVideoFrameCallback((_, first) => {
                video.requestVideoFrameCallback((_, next) => {
                  clearTimeout(timer);
                  resolve(next.mediaTime > first.mediaTime);
                });
              });
            });
          }
        """))

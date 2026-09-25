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
        frame_result = self.page.locator(".inline-reel-card.is-active video").evaluate("""
          async video => {
            await video.play();
            const canvas = document.createElement('canvas');
            canvas.width = 64;
            canvas.height = 64;
            const context = canvas.getContext('2d', {willReadFrequently: true});
            const pixels = () => {
              context.drawImage(video, 0, 0, canvas.width, canvas.height);
              return context.getImageData(0, 0, canvas.width, canvas.height).data;
            };
            const firstTime = video.currentTime;
            const first = new Uint8ClampedArray(pixels());
            let maxPixelDelta = 0;
            for (let attempt = 0; attempt < 8; attempt++) {
              await new Promise(resolve => setTimeout(resolve, 500));
              const next = pixels();
              let delta = 0;
              for (let index = 0; index < next.length; index += 4) {
                delta += Math.abs(next[index] - first[index]);
                delta += Math.abs(next[index + 1] - first[index + 1]);
                delta += Math.abs(next[index + 2] - first[index + 2]);
              }
              maxPixelDelta = Math.max(maxPixelDelta, delta);
              if (maxPixelDelta > 1000) break;
            }
            return {advanced: maxPixelDelta > 1000, maxPixelDelta, firstTime, currentTime: video.currentTime, paused: video.paused, readyState: video.readyState};
          }
        """)
        self.assertTrue(frame_result["advanced"], frame_result)

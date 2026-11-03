// Shared by practice and statistics: one click, UK then US, with a short gap.
const wordAudio = (() => {
    let audio = null;
    let gapTimer = null;

    function stop() {
        window.clearTimeout(gapTimer);
        gapTimer = null;
        if (audio) {
            audio.onended = null;
            audio.onerror = null;
            audio.pause();
            audio = null;
        }
    }

    return {
        hasWordAudio(word) {
            return Boolean(word?.audio_urls?.uk || word?.audio_urls?.us);
        },
        stopWordAudio: stop,
        playWord(word) {
            stop();
            this.audioError = '';
            const urls = [word?.audio_urls?.uk, word?.audio_urls?.us].filter(Boolean);
            const next = () => {
                const current = audio = new Audio(urls.shift());
                const failed = () => {
                    if (audio !== current) return;
                    stop();
                    this.audioError = '读音播放失败，请重试。';
                };
                current.onended = () => {
                    audio = null;
                    if (urls.length) gapTimer = window.setTimeout(next, 500);
                };
                current.onerror = failed;
                current.play().catch(failed);
            };
            if (urls.length) next();
        }
    };
})();

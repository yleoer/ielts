const { createApp } = Vue;
const illustrationPreloads = new Map();

const practiceApp = {
    data() {
        return {
            ...workspaceControls.data(),
            words: [], currentIndex: 0, userInput: '', isChecking: false,
            showAnswer: false, isCorrect: false, feedbackMessage: '', isFinished: false,
            isPracticeAbandoned: false, isComposing: false, isLoadingWords: false,
            isAdvancing: false, advanceTimer: null,
            lastWrongInput: '', shake: false, shakeTimer: null, wordsError: '',
            illustrationFailed: false, audioError: '', otherSensesExpanded: false, sensePointerType: '', sessionId: '',
            practiceMode: 'normal', summary: null,
            pendingAttempt: null, submitError: '', submissionConflict: false,
            answerAccepted: false,
            clockStartedAt: null, elapsedMs: 0, firstInputMs: null,
            stats: { correct: 0, incorrect: 0, errors: [] },
            // Results and the waiting page re-read the local plan; clockNow drives the countdown text.
            planTimer: null, clockNow: Date.now(),
            // Relative on purpose: axios rejects absolute URLs with the cijian: scheme used on Linux,
            // while a relative path resolves to the page's own origin on every platform.
            apiBaseUrl: '/api'
        };
    },
    computed: {
        ...workspaceControls.computed,
        currentWord() { return this.words[this.currentIndex] || null; },
        currentChineseSenses() { return this.currentWord?.chinese_senses || []; },
        primaryChineseSense() { return this.currentChineseSenses[0] || null; },
        secondaryChineseSenses() { return this.currentChineseSenses.slice(1, 3); },
        remainingChineseSenses() { return this.currentChineseSenses.slice(3); },
        isMistakePractice() { return this.practiceMode === 'mistakes'; },
        isDifficultPractice() { return this.practiceMode === 'difficult'; },
        isStalePractice() { return this.practiceMode === 'stale'; },
        isFormalPractice() { return this.practiceMode === 'normal'; },
        titlebarNote() {
            if (this.isMistakePractice) return '错词重练 · 不计入记忆与统计';
            if (this.isDifficultPractice) return '难点突破 · 最多 20 个';
            if (this.isStalePractice) return '久未练习 · 最多 20 个';
            if (!this.isFormalPractice) return '自由练习 · 最多 20 个';
            return this.summary ? `待复习 ${this.summary.due_count || 0} 个 · 新词 ${this.summary.new_available || 0} 个` : '';
        },
        // The waiting page: no question, nothing loading or failing, no unsaved answer.
        isIdle() { return !this.isFinished && !this.currentWord && !this.isLoadingWords && !this.wordsError && !this.pendingAttempt; },
        watchesPlan() { return this.isFinished || this.isIdle; },
        planCount() { return (this.summary?.due_count || 0) + (this.summary?.new_available || 0); },
        planReady() { return this.isIdle && this.isFormalPractice && this.planCount > 0; },
        planText() {
            const due = this.summary?.due_count || 0, fresh = this.summary?.new_available || 0;
            return [due && `待复习 ${due} 个`, fresh && `新词 ${fresh} 个`].filter(Boolean).join(' · ');
        },
        planActionLabel() { return this.summary?.due_count ? '开始复习' : '开始学习'; },
        planStatusText() { return this.planCount ? this.planText : this.nextDueText ? `下次复习 ${this.nextDueText}` : ''; },
        // Keep the bar while a round is loading its next word, hide it on the waiting page.
        showProgress() { return Boolean(this.currentWord) || this.attemptedTotal > 0; },
        progressTotal() {
            if (!this.isFormalPractice) return this.words.length;
            return Math.max(this.words.length, this.currentIndex + this.planCount);
        },
        progressCurrent() { return this.currentWord ? this.currentIndex + 1 : this.attemptedTotal; },
        progressPercentage() { return this.progressTotal ? this.progressCurrent * 100 / this.progressTotal : 0; },
        attemptedTotal() { return this.stats.correct + this.stats.incorrect; },
        accuracy() { return this.attemptedTotal ? Math.round(this.stats.correct * 100 / this.attemptedTotal) : 0; },
        mistakePracticeWords() {
            return [...new Map(this.stats.errors.map(error => [error.wordData.source_id || error.word, error.wordData])).values()];
        },
        cardClass() { return this.isAdvancing ? 'is-success' : this.showAnswer ? 'is-correction' : ''; },
        inputClass() {
            return [this.isAdvancing ? 'is-correct' : this.showAnswer ? 'is-invalid' : 'is-pending', this.shake ? 'practice-shake' : ''];
        },
        nextDueText() { return this.summary?.next_due ? this.formatDueTime(this.summary.next_due, this.clockNow) : ''; },
        answerDisplay() {
            const candidates = String(this.currentWord?.word || '').split('/').map(value => value.trim()).filter(Boolean);
            const input = this.normalizeAnswer(this.lastWrongInput);
            const best = candidates.reduce((best, candidate) => !best || this.levenshteinDistance(candidate.toLowerCase(), input) < this.levenshteinDistance(best.toLowerCase(), input) ? candidate : best, '');
            return { segments: this.alignAnswer(best, input), alternatives: candidates.filter(value => value !== best).join(' / ') };
        }
    },
    watch: {
        currentWord() { this.stopWordAudio(); this.audioError = ''; this.illustrationFailed = false; this.otherSensesExpanded = false; },
        // The answer panel grows below the input; keep it visible in short desktop windows.
        showAnswer(shown) {
            if (shown) this.$nextTick(() => document.querySelector?.('.correction-area')?.scrollIntoView({ block: 'nearest' }));
        },
        watchesPlan(active) { if (active) this.schedulePlanCheck(); else this.clearPlanTimer(); },
        summary() { if (this.watchesPlan) this.schedulePlanCheck(); },
        isFinished(finished) { if (finished) this.revealResults(); },
        planReady(ready) { if (ready) this.focusPlanAction(); }
    },
    methods: {
        ...workspaceControls.methods,
        ...wordAudio,
        playPracticeWord(word, event) {
            this.playWord(word);
            if (event.detail > 0) this.focusInput();
        },
        rememberSensePointer(event) { this.sensePointerType = event.pointerType || ''; },
        toggleOtherSenses(event) {
            if (!this.remainingChineseSenses.length) return;
            this.otherSensesExpanded = !this.otherSensesExpanded;
            const returnToInput = event.detail > 0 && (event.pointerType || this.sensePointerType) === 'mouse';
            this.sensePointerType = '';
            // Mouse users can resume typing; keyboard and touch retain native focus.
            if (returnToInput) this.$nextTick(() => this.$refs.inputField?.focus({ preventScroll: true }));
        },
        cloneWord(word) { return JSON.parse(JSON.stringify(word)); },
        isRetypeCorrect() { return Boolean(this.userInput.trim()) && this.answerCandidates(this.currentWord?.word).includes(this.normalizeAnswer(this.userInput)); },
        resetSession(mode) {
            this.stopWordAudio();
            this.pauseClock();
            this.sessionId = crypto.randomUUID();
            this.practiceMode = mode;
            this.words = [];
            this.currentIndex = 0;
            this.isFinished = false;
            this.isPracticeAbandoned = false;
            this.stats = { correct: 0, incorrect: 0, errors: [] };
            this.resetInputState();
        },
        async fetchWords({ mode = 'normal' } = {}) {
            if (this.pendingAttempt || this.isLoadingWords || this.isChecking) return;
            this.resetSession(mode);
            this.summary = null;
            await this.loadNextWord();
        },
        // Leave results or an empty extra mode for the waiting page without starting a round.
        returnToPlan() {
            if (this.pendingAttempt) return;
            this.resetSession('normal');
            return this.refreshSummary();
        },
        // Results stay until dismissed; hiding the window to the tray counts as done.
        closeResults() { if (this.isFinished) this.returnToPlan(); },
        continuePlan() { return this.planCount ? this.fetchWords() : this.returnToPlan(); },
        // Long results open at the top. Focus the sheet rather than the button at its bottom, so
        // Space and arrows scroll the review while Enter on the sheet still runs the main action.
        revealResults() {
            this.$nextTick(() => {
                this.$refs.resultsSheet?.focus({ preventScroll: true });
                if (this.$refs.practiceMain) this.$refs.practiceMain.scrollTop = 0;
            });
        },
        focusPlanAction() {
            this.$nextTick(() => {
                const active = document.activeElement;
                if (!active || active === document.body) this.$refs.planAction?.focus();
            });
        },
        // Re-read the plan at the next due time and at least once a minute, which also
        // picks up words added by background sync and keeps the countdown current.
        schedulePlanCheck() {
            this.clearPlanTimer();
            this.clockNow = Date.now();
            if (!this.watchesPlan) return;
            const untilDue = Date.parse(this.summary?.next_due || '') - this.clockNow;
            const wait = untilDue > 0 ? Math.min(untilDue + 200, 60000) : 60000;
            this.planTimer = window.setTimeout(() => { this.planTimer = null; this.checkPlan(); }, wait);
        },
        clearPlanTimer() {
            if (this.planTimer) window.clearTimeout(this.planTimer);
            this.planTimer = null;
        },
        async checkPlan() {
            if (this.watchesPlan) await this.refreshSummary();
            this.schedulePlanCheck();
        },
        formatDueTime(value, now) {
            const minutes = Math.max(1, Math.ceil((new Date(value) - now) / 60000));
            const left = minutes === 1 ? '1 分钟内'
                : minutes < 60 ? `${minutes} 分钟后`
                : minutes < 1440 ? `${Math.floor(minutes / 60)} 小时${minutes % 60 ? ` ${minutes % 60} 分钟` : ''}后`
                : `${Math.floor(minutes / 1440)} 天后`;
            return `${this.formatDateTime(value, now)}（${left}）`;
        },
        async loadNextWord() {
            if (this.isLoadingWords || this.pendingAttempt) return;
            this.isLoadingWords = true;
            this.wordsError = '';
            try {
                const data = (await axios.get(`${this.apiBaseUrl}/practice/queue`, {
                    params: { session_id: this.sessionId, limit: this.isFormalPractice ? 3 : 20,
                        mode: this.isFormalPractice ? 'scheduled' : this.practiceMode }, timeout: 15000
                })).data.data;
                this.summary = data.summary;
                this.preloadIllustrations(data.items);
                if (!data.items.length) {
                    if (this.attemptedTotal) this.finishPractice();
                    return;
                }
                // Remaining formal items only warm media; after each saved answer
                // the core selects the next real item again.
                this.words.push(...(this.isFormalPractice ? data.items.slice(0, 1) : data.items));
                this.resetInputState();
                await this.$nextTick();
                this.beginCurrentWord();
                this.focusInput();
            } catch (error) {
                this.wordsError = error.response?.data?.error || '无法加载单词，请检查连接后重试。';
            } finally {
                this.isLoadingWords = false;
            }
        },
        async refreshSummary() {
            try {
                const response = await axios.get(`${this.apiBaseUrl}/memory/summary`, { timeout: 15000 });
                this.summary = response.data.data;
            } catch (error) { /* Existing counts stay visible; the next queue request retries. */ }
        },
        beginCurrentWord() {
            this.elapsedMs = 0;
            this.firstInputMs = null;
            this.clockStartedAt = null;
            this.preloadIllustrations(this.words.slice(this.currentIndex, this.currentIndex + 3));
            this.resumeClock();
        },
        preloadIllustrations(words) {
            for (const word of words.slice(0, 3)) {
                const url = word.illustration_url;
                if (!url || illustrationPreloads.has(url)) continue;
                const picture = new Image();
                picture.decoding = 'async';
                picture.onload = () => picture.decode().catch(() => {});
                picture.onerror = () => { illustrationPreloads.delete(url); };
                illustrationPreloads.set(url, picture);
                picture.src = url;
                if (illustrationPreloads.size > 32) illustrationPreloads.delete(illustrationPreloads.keys().next().value);
            }
        },
        resumeClock() {
            if (this.clockStartedAt === null && !document.hidden && !this.windowHidden && !this.syncModal.visible && !this.setup.visible && this.currentWord && !this.pendingAttempt && !this.answerAccepted && !this.showAnswer && !this.isFinished) this.clockStartedAt = performance.now();
        },
        pauseClock() {
            if (this.clockStartedAt !== null) {
                this.elapsedMs += Math.max(0, performance.now() - this.clockStartedAt);
                this.clockStartedAt = null;
            }
        },
        effectiveDuration() {
            return this.elapsedMs + (this.clockStartedAt === null ? 0 : Math.max(0, performance.now() - this.clockStartedAt));
        },
        handleBeforeInput(event) {
            if (this.isChecking || this.pendingAttempt || this.isAdvancing || (this.answerAccepted && !this.showAnswer) || (event.data && this.sanitizeInput(event.data) !== event.data)) event.preventDefault();
        },
        handleInput() {
            this.userInput = this.sanitizeInput(this.userInput);
            if (!this.showAnswer && this.firstInputMs === null && this.userInput) this.firstInputMs = this.effectiveDuration();
        },
        handleCompositionStart() { this.isComposing = true; },
        handleCompositionEnd() { this.isComposing = false; this.handleInput(); },
        handleKeydown(event) {
            if (this.isAdvancing || this.isChecking || this.pendingAttempt) { event.preventDefault(); return; }
            if (event.key === 'Enter') this.handleEnter(event);
            if ((event.key === ' ' || event.code === 'Space') && !this.userInput.trim()) {
                event.preventDefault();
                if (!this.showAnswer) this.skipWord();
            }
        },
        handleEnter(event) {
            event.preventDefault();
            if (this.isComposing || this.isAdvancing || this.isChecking || this.pendingAttempt) return;
            if (this.showAnswer) {
                if (!this.userInput.trim() || this.isRetypeCorrect()) this.nextWord();
                else this.triggerShake();
            } else this.submitAnswer();
        },
        submitAnswer() {
            const input = this.sanitizeInput(this.userInput).trim();
            if (!input || !this.isValidAnswerInput(input)) return;
            this.submitInput(input);
        },
        skipWord() { if (!this.showAnswer) this.submitInput(''); },
        async submitInput(input) {
            if (!this.currentWord || this.pendingAttempt || this.isChecking || this.answerAccepted || this.showAnswer) return;
            this.pauseClock();
            // Mistake practice retypes this round's errors; every other mode saves its first answer.
            if (this.isMistakePractice) {
                this.acceptAnswer({ is_correct: Boolean(input) && this.answerCandidates(this.currentWord.word).includes(this.normalizeAnswer(input)) }, input);
                return;
            }
            this.pendingAttempt = {
                attempt_id: this.currentWord.attempt_id, session_id: this.sessionId,
                user_input: input, duration_ms: this.elapsedMs, first_input_ms: this.firstInputMs,
                reviewed_at: new Date().toISOString()
            };
            this.submissionConflict = false;
            await this.retryPending();
        },
        // The core runs locally and answers in milliseconds; a failure is a rejected
        // question (conflict) or a storage error, kept in memory until retried or skipped.
        async retryPending() {
            if (!this.pendingAttempt || this.isChecking || this.submissionConflict) return;
            this.submitError = '';
            this.isChecking = true;
            const payload = this.pendingAttempt;
            try {
                const response = await axios.post(`${this.apiBaseUrl}/practice/attempts`, payload, { timeout: 15000 });
                this.pendingAttempt = null;
                this.acceptAnswer(response.data.data, payload.user_input);
            } catch (error) {
                this.submitError = error.response?.data?.error || '答案未能保存，请重试。';
                this.submissionConflict = [400, 409, 410].includes(error.response?.status);
            } finally {
                this.isChecking = false;
                this.focusInput();
            }
        },
        updateAnswerFeedback(correct, input) {
            this.isCorrect = correct;
            this.showAnswer = !correct;
            this.lastWrongInput = correct ? '' : input;
            this.feedbackMessage = correct ? '' : input ? '拼写错误，正确答案：' : '正确答案：';
        },
        acceptAnswer(result, input) {
            if (result.is_correct) this.stats.correct++;
            else {
                const word = this.cloneWord(this.currentWord);
                this.stats.incorrect++;
                this.stats.errors.push({ word: word.word, meaning: word.chinese_meaning, user_input: input || '(看答案)', wordData: word });
            }
            this.answerAccepted = true;
            this.updateAnswerFeedback(result.is_correct, input);
            this.userInput = '';
            if (result.is_correct) this.startCorrectAdvance();
            else { this.triggerShake(); this.focusInput(); }
        },
        async continueAfterConflict() {
            if (!this.submissionConflict || this.isChecking) return;
            this.pendingAttempt = null;
            this.words.splice(this.currentIndex, 1);
            this.resetInputState();
            if (this.isFormalPractice) await this.loadNextWord();
            else if (this.currentWord) { this.beginCurrentWord(); this.focusInput(); }
            else this.finishPractice();
        },
        resetInputState() {
            this.clearAdvanceTimer();
            this.pauseClock();
            this.otherSensesExpanded = false;
            this.userInput = '';
            this.showAnswer = false;
            this.answerAccepted = false;
            this.isCorrect = false;
            this.lastWrongInput = '';
            this.feedbackMessage = '';
            this.submitError = '';
            this.submissionConflict = false;
            this.shake = false;
        },
        startCorrectAdvance(delay = 180) {
            this.clearAdvanceTimer();
            this.isAdvancing = true;
            this.advanceTimer = window.setTimeout(() => { this.advanceTimer = null; this.nextWord(); }, delay);
        },
        clearAdvanceTimer() {
            if (this.advanceTimer) window.clearTimeout(this.advanceTimer);
            this.advanceTimer = null;
            this.isAdvancing = false;
        },
        async nextWord() {
            if (this.pendingAttempt || this.isLoadingWords || !this.answerAccepted) return;
            this.clearAdvanceTimer();
            this.currentIndex++;
            this.resetInputState();
            if (this.isFormalPractice) {
                await this.loadNextWord();
            } else if (this.currentWord) {
                this.beginCurrentWord(); this.focusInput();
            } else this.finishPractice();
        },
        finishPractice({ abandoned = false } = {}) {
            if (this.pendingAttempt) return;
            // A round without saved answers has nothing to review.
            if (!this.attemptedTotal) { this.returnToPlan(); return; }
            this.clearAdvanceTimer();
            this.stopWordAudio();
            this.pauseClock();
            this.isFinished = true;
            this.isPracticeAbandoned = abandoned;
            this.refreshSummary();
        },
        restartPractice() { this.fetchWords(); },
        startFreePractice() { this.fetchWords({ mode: 'free' }); },
        startDifficultPractice() { return this.fetchWords({ mode: 'difficult' }); },
        startStalePractice() { return this.fetchWords({ mode: 'stale' }); },
        startMistakePractice() {
            const words = this.mistakePracticeWords.map(word => this.cloneWord(word));
            if (!words.length || this.pendingAttempt) return;
            this.resetSession('mistakes');
            this.words = words;
            this.beginCurrentWord(); this.focusInput();
        },
        quitPractice() {
            if (this.pendingAttempt) { this.submitError = '请先重试保存或处理失效题目，再退出练习。'; return; }
            this.finishPractice({ abandoned: true });
        },
        focusInput() { this.$nextTick(() => this.$refs.inputField?.focus()); },
        alignAnswer(expected, input) {
            const chars = Array.from(expected);
            if (!input) {
                return chars.map((ch) => ({ ch, ok: true }));
            }

            const left = chars.map((ch) => ch.toLowerCase());
            const right = Array.from(input);
            const rows = left.length;
            const cols = right.length;
            const dp = Array.from({ length: rows + 1 }, () => new Array(cols + 1).fill(0));
            for (let i = rows - 1; i >= 0; i--) {
                for (let j = cols - 1; j >= 0; j--) {
                    dp[i][j] = left[i] === right[j]
                        ? dp[i + 1][j + 1] + 1
                        : Math.max(dp[i + 1][j], dp[i][j + 1]);
                }
            }

            const matched = new Array(rows).fill(false);
            let i = 0;
            let j = 0;
            while (i < rows && j < cols) {
                if (left[i] === right[j]) {
                    matched[i] = true;
                    i++;
                    j++;
                } else if (dp[i + 1][j] >= dp[i][j + 1]) {
                    i++;
                } else {
                    j++;
                }
            }

            return chars.map((ch, index) => ({
                ch,
                ok: matched[index] || !/[a-z]/i.test(ch)
            }));
        },

        triggerShake() {
            if (this.shakeTimer) {
                window.clearTimeout(this.shakeTimer);
            }
            this.shake = false;
            this.$nextTick(() => {
                this.shake = true;
                this.shakeTimer = window.setTimeout(() => {
                    this.shake = false;
                    this.shakeTimer = null;
                }, 320);
            });
        },
        sanitizeInput(value) {
            return String(value || '').replace(/[^a-zA-Z\s'-]/g, '').replace(/\s+/g, ' ');
        },

        isValidAnswerInput(value) {
            const normalized = this.sanitizeInput(value).trim();
            return /^[a-zA-Z][a-zA-Z\s'-]*$/.test(normalized);
        },

        normalizeAnswer(value) {
            return this.sanitizeInput(value).trim().toLowerCase();
        },

        answerCandidates(expected) {
            return String(expected || '')
                .split('/')
                .map(candidate => this.normalizeAnswer(candidate))
                .filter(Boolean);
        },

        levenshteinDistance(left, right) {
            const previous = Array.from({ length: right.length + 1 }, (_, index) => index);
            const current = new Array(right.length + 1).fill(0);

            for (let i = 1; i <= left.length; i++) {
                current[0] = i;
                for (let j = 1; j <= right.length; j++) {
                    const cost = left[i - 1] === right[j - 1] ? 0 : 1;
                    current[j] = Math.min(
                        current[j - 1] + 1,
                        previous[j] + 1,
                        previous[j - 1] + cost
                    );
                }
                for (let j = 0; j < current.length; j++) {
                    previous[j] = current[j];
                }
            }

            return previous[right.length];
        },

        async refreshResourceUrls() {
            if (!this.words.length) return;
            const items = (await axios.post(`${this.apiBaseUrl}/resources/urls`, { ids: this.words.map(w => w.id) })).data.data;
            for (const item of items) {
                const word = this.words.find(w => w.id === item.id);
                if (word) Object.assign(word, { illustration_url: item.illustration_url, audio_url: item.audio_url, audio_urls: item.audio_urls });
            }
            this.illustrationFailed = false;
        },
        // First launch: ask for the server before loading practice. Returns true when setup is needed.
        async checkServerSetup() {
            const settings = await this.loadServerSettings();
            if (settings.configured) return false;
            await this.openSyncModal();
            return true;
        },

        async refreshPageData() {
            if (this.isLoadingWords) return;
            // Keep pending answers, correction feedback and fixed practice batches intact.
            if (this.pendingAttempt || this.isChecking || (this.answerAccepted && !this.isFinished) || !this.isFormalPractice) {
                await this.refreshSummary();
                return;
            }
            if (this.answerAccepted) this.currentIndex++;
            this.resetInputState();
            this.words.splice(this.currentIndex);
            this.isFinished = false;
            this.isPracticeAbandoned = false;
            await this.loadNextWord();
        },

        // Synced answers from another device may already have reviewed the word on screen:
        // show the core's current pick unless typing has started (a stale submit then conflicts).
        async afterSync() {
            if (this.currentWord && this.isFormalPractice && !this.isFinished && !this.userInput && !this.answerAccepted) await this.refreshPageData();
            else await this.refreshSummary();
        },
    },
    async mounted() {
        this.initUpdates();
        this.initDesktopShell();
        const needsSetup = await this.checkServerSetup();
        if (!needsSetup) await this.fetchWords();
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) { this.stopWordAudio(); this.pauseClock(); }
            else { this.resumeClock(); this.checkPlan(); }
        });
        window.addEventListener('pagehide', this.stopWordAudio);
        window.addEventListener('keydown', event => {
            if (event.target !== document.body || this.workspaceModalOpen) return;
            if (event.code === 'Space') event.preventDefault();
            if (event.key === 'Enter' && this.showAnswer) this.handleEnter(event);
            if (/^[a-zA-Z]$/.test(event.key) && !event.ctrlKey && !event.metaKey && !event.altKey && !this.isFinished) this.focusInput();
        });
    }
};
createApp(practiceApp).mount('#app');

const { createApp } = Vue;
const DRAFT_PREFIX = 'typingPracticeDraftSession:fsrs:v1:';
const OUTBOX_PREFIX = 'typingPracticePending:fsrs:v1:';
const ACTIVE_KEY = 'typingPracticeActiveSession:fsrs:v1';

const practiceApp = {
    data() {
        return {
            words: [], currentIndex: 0, userInput: '', isChecking: false,
            showAnswer: false, isCorrect: false, feedbackMessage: '', isFinished: false,
            isPracticeAbandoned: false, isComposing: false, isLoadingWords: false,
            isAdvancing: false, isRestoringDraft: false, advanceTimer: null,
            lastWrongInput: '', shake: false, shakeTimer: null, wordsError: '',
            illustrationFailed: false, sessionId: '', sessionLimit: 20,
            practiceMode: 'normal', summary: null,
            pendingAttempt: null, submitError: '', submissionConflict: false,
            answerAccepted: false, storageError: '', draftSaveTimer: null,
            clockStartedAt: null, elapsedMs: 0, firstInputMs: null,
            serverOffset: 0,
            stats: { correct: 0, incorrect: 0, errors: [], attempts: [] },
            syncModal: { visible: false, loading: false, syncing: false, error: '', status: null },
            apiBaseUrl: `${window.location.origin}/api`
        };
    },
    computed: {
        currentWord() { return this.words[this.currentIndex] || null; },
        isMistakePractice() { return this.practiceMode === 'mistakes'; },
        isFormalPractice() { return this.practiceMode === 'normal'; },
        progressTotal() { return this.isFormalPractice ? this.sessionLimit : this.words.length; },
        progressCurrent() { return this.currentWord ? this.currentIndex + 1 : this.attemptedTotal; },
        progressPercentage() { return this.progressTotal ? this.progressCurrent * 100 / this.progressTotal : 0; },
        attemptedTotal() { return this.stats.correct + this.stats.incorrect; },
        accuracy() { return this.attemptedTotal ? Math.round(this.stats.correct * 100 / this.attemptedTotal) : 0; },
        resultTotal() { return this.attemptedTotal; },
        mistakePracticeWords() {
            return [...new Map(this.stats.errors.map(error => [error.wordData.source_id || error.word, error.wordData])).values()];
        },
        cardClass() { return this.isAdvancing ? 'is-success' : this.showAnswer ? 'is-correction' : ''; },
        inputClass() {
            return [this.isAdvancing ? 'is-correct' : this.showAnswer ? 'is-invalid' : 'is-pending', this.shake ? 'practice-shake' : ''];
        },
        answerOkClass() { return 'answer-letter'; },
        answerMissClass() { return 'answer-letter is-missed'; },
        wrongInput() { return this.lastWrongInput; },
        nextDueText() { return this.summary?.next_due ? this.formatSyncTime(this.summary.next_due) : ''; },
        answerDisplay() {
            const candidates = String(this.currentWord?.word || '').split('/').map(value => value.trim()).filter(Boolean);
            const input = this.normalizeAnswer(this.lastWrongInput);
            const best = candidates.reduce((best, candidate) => !best || this.levenshteinDistance(candidate.toLowerCase(), input) < this.levenshteinDistance(best.toLowerCase(), input) ? candidate : best, '');
            return { segments: this.alignAnswer(best, input), alternatives: candidates.filter(value => value !== best).join(' / ') };
        }
    },
    watch: {
        currentWord() { this.illustrationFailed = false; },
        userInput() {
            if (this.isRestoringDraft) return;
            if (this.showAnswer && !this.isAdvancing && !this.isComposing && this.isRetypeCorrect()) {
                this.startCorrectAdvance();
            } else {
                this.scheduleDraftSave();
            }
        }
    },
    methods: {
        t(zh) { return zh; },
        generateSessionId() { return crypto.randomUUID ? crypto.randomUUID() : 's-' + Date.now() + '-' + Math.random().toString(36).slice(2); },
        cloneWord(word) { return JSON.parse(JSON.stringify(word)); },
        isRetypeCorrect() { return Boolean(this.userInput.trim()) && this.answerCandidates(this.currentWord?.word).includes(this.normalizeAnswer(this.userInput)); },
        async fetchWords({ mode = 'normal' } = {}) {
            if (this.pendingAttempt || this.isLoadingWords || this.isChecking) return;
            this.clearAdvanceTimer();
            this.pauseClock();
            this.clearDraftSession();
            this.sessionId = this.generateSessionId();
            this.practiceMode = mode;
            this.words = [];
            this.currentIndex = 0;
            this.isFinished = false;
            this.isPracticeAbandoned = false;
            this.stats = { correct: 0, incorrect: 0, errors: [], attempts: [] };
            this.resetInputState();
            await this.loadNextWord();
        },
        async loadNextWord() {
            if (this.isLoadingWords || this.pendingAttempt) return;
            this.isLoadingWords = true;
            this.wordsError = '';
            try {
                const response = await axios.get(`${this.apiBaseUrl}/practice/queue`, {
                    params: { session_id: this.sessionId, limit: this.isFormalPractice ? 1 : this.sessionLimit, mode: this.isFormalPractice ? 'scheduled' : 'free' }, timeout: 15000
                });
                const data = response.data.data;
                this.serverOffset = Date.parse(data.server_time) - Date.now();
                this.summary = data.summary;
                this.sessionLimit = response.data.session_limit || 20;
                if (!data.items.length) {
                    if (this.attemptedTotal) this.finishPractice();
                    return;
                }
                this.words.push(...data.items);
                this.resetInputState();
                await this.$nextTick();
                this.beginCurrentWord();
                this.focusInput();
                this.saveDraftSession();
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
            this.resumeClock();
        },
        resumeClock() {
            if (this.clockStartedAt === null && !document.hidden && !this.syncModal.visible && this.currentWord && !this.pendingAttempt && !this.answerAccepted && !this.showAnswer && !this.isFinished) this.clockStartedAt = performance.now();
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
            if (this.pendingAttempt || (this.answerAccepted && !this.showAnswer) || this.isAdvancing || (event.data && this.sanitizeInput(event.data) !== event.data)) event.preventDefault();
        },
        handleInput() {
            this.userInput = this.sanitizeInput(this.userInput);
            if (!this.showAnswer && !this.pendingAttempt && this.firstInputMs === null && this.userInput) this.firstInputMs = this.effectiveDuration();
        },
        handleCompositionStart() { this.isComposing = true; },
        handleCompositionEnd() { this.isComposing = false; this.handleInput(); this.scheduleDraftSave(); },
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
            if (this.isComposing || this.isAdvancing || this.pendingAttempt || this.isChecking) return;
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
            if (!this.isFormalPractice) {
                this.acceptAnswer({ is_correct: Boolean(input) && this.answerCandidates(this.currentWord.word).includes(this.normalizeAnswer(input)), duration_ms: this.elapsedMs }, input);
                return;
            }
            this.pendingAttempt = {
                attempt_id: this.currentWord.attempt_id, session_id: this.sessionId,
                user_input: input, duration_ms: this.elapsedMs, first_input_ms: this.firstInputMs,
                reviewed_at: new Date(Date.now() + this.serverOffset).toISOString()
            };
            this.submissionConflict = false;
            await this.retryPending();
        },
        async retryPending() {
            if (!this.pendingAttempt || this.isChecking || this.submissionConflict) return;
            this.submitError = '';
            if (!this.saveDraftSession()) return;
            this.isChecking = true;
            const payload = { ...this.pendingAttempt };
            try {
                const response = await axios.post(`${this.apiBaseUrl}/practice/attempts`, payload, { timeout: 15000 });
                this.pendingAttempt = null;
                this.acceptAnswer(response.data.data, payload.user_input);
                // Only remove the durable outbox after the acknowledged UI state was saved.
                if (this.saveDraftSession()) this.removeConfirmedOutbox(payload.attempt_id);
            } catch (error) {
                this.submitError = error.response?.data?.error || '答案尚未确认保存，请检查连接后重试。';
                this.submissionConflict = [400, 409, 410].includes(error.response?.status);
                this.saveDraftSession();
            } finally {
                this.isChecking = false;
                this.focusInput();
            }
        },
        acceptAnswer(result, input) {
            const word = this.cloneWord(this.currentWord);
            const existing = result.attempt_id && this.stats.attempts.some(item => item.attempt_id === result.attempt_id);
            if (!existing) {
                this.stats.attempts.push({ attempt_id: result.attempt_id });
                if (result.is_correct) this.stats.correct++;
                else {
                    this.stats.incorrect++;
                    this.stats.errors.push({ word: word.word, meaning: word.chinese_meaning, user_input: input || '(看答案)', wordData: word });
                }
            }
            this.answerAccepted = true;
            this.isCorrect = result.is_correct;
            this.showAnswer = !result.is_correct;
            this.lastWrongInput = result.is_correct ? '' : input;
            this.feedbackMessage = result.is_correct ? '' : input ? '拼写错误，正确答案：' : '正确答案：';
            this.userInput = '';
            const saved = this.saveDraftSession();
            if (result.is_correct && saved) this.startCorrectAdvance();
            else { this.triggerShake(); this.focusInput(); }
        },
        removeConfirmedOutbox(attemptId) {
            try { localStorage.removeItem(OUTBOX_PREFIX + attemptId); }
            catch (error) { this.storageError = '答案已保存，但浏览器进度未能更新，请重试保存进度。'; }
        },
        retryDraftSave() {
            if (!this.saveDraftSession()) return;
            if (this.answerAccepted) {
                const id = this.stats.attempts.at(-1)?.attempt_id;
                if (id) this.removeConfirmedOutbox(id);
                if (this.isCorrect) this.startCorrectAdvance();
            }
        },
        async continueAfterConflict() {
            if (!this.submissionConflict || this.isChecking) return;
            localStorage.removeItem(OUTBOX_PREFIX + this.pendingAttempt.attempt_id);
            this.pendingAttempt = null;
            this.words.splice(this.currentIndex, 1);
            this.resetInputState();
            this.saveDraftSession();
            await this.loadNextWord();
        },
        resetInputState() {
            this.clearAdvanceTimer();
            this.pauseClock();
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
        startCorrectAdvance() {
            this.clearAdvanceTimer();
            this.isAdvancing = true;
            this.advanceTimer = window.setTimeout(() => { this.advanceTimer = null; this.nextWord(); }, 180);
        },
        clearAdvanceTimer() {
            if (this.advanceTimer) window.clearTimeout(this.advanceTimer);
            this.advanceTimer = null;
            this.isAdvancing = false;
        },
        async nextWord() {
            if (this.pendingAttempt || this.isLoadingWords || this.storageError || !this.answerAccepted) return;
            this.clearAdvanceTimer();
            this.currentIndex++;
            this.resetInputState();
            this.saveDraftSession();
            if (this.isFormalPractice) {
                if (this.attemptedTotal >= this.sessionLimit) this.finishPractice();
                else await this.loadNextWord();
            } else if (this.currentWord) {
                this.beginCurrentWord(); this.focusInput(); this.saveDraftSession();
            } else this.finishPractice();
        },
        finishPractice({ abandoned = false } = {}) {
            if (this.pendingAttempt) return;
            this.clearAdvanceTimer();
            this.pauseClock();
            this.isFinished = true;
            this.isPracticeAbandoned = abandoned;
            this.clearDraftSession();
            this.refreshSummary();
        },
        restartPractice() { this.fetchWords(); },
        startFreePractice() { this.fetchWords({ mode: 'free' }); },
        startMistakePractice() {
            const words = this.mistakePracticeWords.map(word => this.cloneWord(word));
            if (!words.length || this.pendingAttempt) return;
            this.clearDraftSession();
            this.sessionId = this.generateSessionId();
            this.practiceMode = 'mistakes';
            this.words = words;
            this.currentIndex = 0;
            this.isFinished = false;
            this.isPracticeAbandoned = false;
            this.stats = { correct: 0, incorrect: 0, errors: [], attempts: [] };
            this.resetInputState();
            this.beginCurrentWord(); this.focusInput(); this.saveDraftSession();
        },
        quitPractice() {
            if (this.pendingAttempt) { this.submitError = '请先重试保存或处理失效题目，再退出练习。'; return; }
            if (confirm('确定要退出练习吗？已保存的作答会保留。')) this.finishPractice({ abandoned: true });
        },
        focusInput() { this.$nextTick(() => this.$refs.inputField?.focus()); },
        scheduleDraftSave() {
            if (this.draftSaveTimer) window.clearTimeout(this.draftSaveTimer);
            this.draftSaveTimer = window.setTimeout(() => { this.draftSaveTimer = null; this.saveDraftSession(); }, 200);
        },
        saveDraftSession() {
            if (!this.sessionId || this.isRestoringDraft || this.isFinished) return false;
            const draft = {
                version: 1, savedAt: new Date().toISOString(), sessionId: this.sessionId,
                words: this.words, currentIndex: this.currentIndex, sessionLimit: this.sessionLimit,
                userInput: this.userInput, showAnswer: this.showAnswer, answerAccepted: this.answerAccepted,
                isCorrect: this.isCorrect, lastWrongInput: this.lastWrongInput, feedbackMessage: this.feedbackMessage,
                practiceMode: this.practiceMode, stats: this.stats, elapsedMs: this.effectiveDuration(),
                firstInputMs: this.firstInputMs, serverOffset: this.serverOffset, summary: this.summary,
                pendingAttempt: this.pendingAttempt
            };
            try {
                if (this.pendingAttempt) localStorage.setItem(OUTBOX_PREFIX + this.pendingAttempt.attempt_id, JSON.stringify(draft));
                localStorage.setItem(DRAFT_PREFIX + this.sessionId, JSON.stringify(draft));
                sessionStorage.setItem(ACTIVE_KEY, this.sessionId);
                this.storageError = '';
                return true;
            } catch (error) {
                this.storageError = '浏览器无法保存练习进度，请检查站点存储空间后重试。';
                return false;
            }
        },
        clearDraftSession() {
            if (this.draftSaveTimer) window.clearTimeout(this.draftSaveTimer);
            this.draftSaveTimer = null;
            if (this.pendingAttempt) return;
            try {
                if (this.sessionId) localStorage.removeItem(DRAFT_PREFIX + this.sessionId);
                sessionStorage.removeItem(ACTIVE_KEY);
            } catch (error) { /* Memory-only state still permits exiting. */ }
        },
        async restoreDraftSession() {
            let draft;
            try {
                // Retire old sessions without ever replaying their batch statistics.
                localStorage.removeItem('typingPracticeDraftSession:wordAtlas:v2');
                const active = sessionStorage.getItem(ACTIVE_KEY);
                const keys = Object.keys(localStorage);
                const pending = keys.filter(key => key.startsWith(OUTBOX_PREFIX)).map(key => JSON.parse(localStorage.getItem(key))).sort((a, b) => a.savedAt.localeCompare(b.savedAt));
                const drafts = keys.filter(key => key.startsWith(DRAFT_PREFIX)).map(key => JSON.parse(localStorage.getItem(key))).sort((a, b) => b.savedAt.localeCompare(a.savedAt));
                draft = pending.find(item => item.sessionId === active) || pending[0] || drafts.find(item => item.sessionId === active) || drafts[0];
                if (!draft || draft.version !== 1 || !Array.isArray(draft.words) || !draft.sessionId) return false;
                if (!draft.pendingAttempt && Date.now() - Date.parse(draft.savedAt) > 7 * 86400000) {
                    localStorage.removeItem(DRAFT_PREFIX + draft.sessionId);
                    return false;
                }
            } catch (error) { return false; }
            this.isRestoringDraft = true;
            for (const key of ['sessionId', 'words', 'currentIndex', 'sessionLimit', 'userInput', 'showAnswer', 'answerAccepted', 'isCorrect', 'lastWrongInput', 'feedbackMessage', 'practiceMode', 'stats', 'elapsedMs', 'firstInputMs', 'serverOffset', 'summary', 'pendingAttempt']) {
                if (key in draft) this[key] = draft[key];
            }
            this.clockStartedAt = null;
            await this.$nextTick();
            this.isRestoringDraft = false;
            if (this.pendingAttempt) await this.retryPending();
            else if (this.answerAccepted && !this.showAnswer) await this.nextWord();
            else if (!this.currentWord) {
                if (this.isFormalPractice && this.attemptedTotal < this.sessionLimit) await this.loadNextWord();
                else this.finishPractice();
            } else { this.resumeClock(); this.focusInput(); }
            return true;
        },
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

        async openSyncModal() {
            this.pauseClock();
            this.syncModal.visible = true;
            await this.loadSyncStatus();
        },

        closeSyncModal() {
            this.syncModal.visible = false;
            this.resumeClock();
        },

        async loadSyncStatus() {
            this.syncModal.loading = true;
            this.syncModal.error = '';
            try {
                const response = await axios.get(`${this.apiBaseUrl}/sync/status`);
                this.syncModal.status = response.data.data || null;
            } catch (error) {
                console.error('Error loading sync status:', error);
                this.syncModal.error = '无法加载同步状态';
            } finally {
                this.syncModal.loading = false;
            }
        },

        async syncNow() {
            this.syncModal.syncing = true;
            this.syncModal.error = '';
            try {
                const response = await axios.post(`${this.apiBaseUrl}/sync/now`);
                this.syncModal.status = response.data.data || null;
                await this.refreshSummary();
            } catch (error) {
                console.error('Error syncing Anki collection:', error);
                const message = error.response?.data?.error || '同步失败';
                this.syncModal.error = message;
                if (error.response?.data?.data) {
                    this.syncModal.status = error.response.data.data;
                }
            } finally {
                this.syncModal.syncing = false;
            }
        },

        formatSyncTime(value) {
            if (!value) {
                return '暂无';
            }
            return new Date(value).toLocaleString('zh-CN', {
                hour12: false,
                timeZone: 'Asia/Shanghai'
            });
        },

        syncHistory() {
            return (this.syncModal.status && this.syncModal.status.history) || [];
        },


    },
    async mounted() {
        document.title = '词间 · 练习';
        if (!await this.restoreDraftSession()) await this.fetchWords();
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) { this.pauseClock(); this.saveDraftSession(); }
            else this.resumeClock();
        });
        window.addEventListener('online', () => this.retryPending());
        window.addEventListener('beforeunload', event => {
            this.pauseClock(); this.saveDraftSession();
            if (this.pendingAttempt) { event.preventDefault(); event.returnValue = ''; }
        });
        window.addEventListener('keydown', event => {
            if (event.key === 'Escape' && this.syncModal.visible) { this.closeSyncModal(); return; }
            if (event.target === document.body) {
                if (event.code === 'Space') event.preventDefault();
                if (event.key === 'Enter' && this.showAnswer) this.handleEnter(event);
                if (/^[a-zA-Z]$/.test(event.key) && !event.ctrlKey && !event.metaKey && !event.altKey && !this.isFinished && !this.syncModal.visible) this.focusInput();
            }
        });
    }
};
createApp(practiceApp).mount('#app');

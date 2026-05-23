const { createApp } = Vue;

createApp({
    data() {
        return {
            words: [],
            currentIndex: 0,
            userInput: '',
            isChecking: false,
            showAnswer: false,
            isCorrect: false,
            feedbackMessage: '',
            isFinished: false,
            isPracticeAbandoned: false,
            isComposing: false,
            isLoadingWords: false,
            isAdvancing: false,
            isRestoringDraft: false,
            advanceTimer: null,
            wordsError: '',
            sessionId: '',
            sessionStartedAt: null,
            currentWordStartedAt: 0,
            draftSaveTimer: null,
            draftStorageKey: 'typingPracticeDraftSession:v1',
            practiceMode: 'normal',
            stealthMode: false,
            stats: {
                total: 0,
                correct: 0,
                incorrect: 0,
                errors: [],
                attempts: []
            },
            syncModal: {
                visible: false,
                loading: false,
                syncing: false,
                error: '',
                status: null
            },
            apiBaseUrl: window.location.origin && window.location.origin.startsWith('http')
                ? `${window.location.origin}/api`
                : 'http://localhost:8080/api'
        };
    },
    computed: {
        currentWord() {
            return this.words[this.currentIndex] || null;
        },
        progressPercentage() {
            if (this.words.length === 0) return 0;
            return (this.progressCurrent / this.words.length) * 100;
        },
        progressCurrent() {
            if (this.words.length === 0) return 0;
            return Math.min(this.currentIndex + 1, this.words.length);
        },
        accuracy() {
            if (this.attemptedTotal === 0) return 0;
            return Math.round((this.stats.correct / this.attemptedTotal) * 100);
        },
        attemptedTotal() {
            return this.stats.correct + this.stats.incorrect;
        },
        resultTotal() {
            return this.isPracticeAbandoned ? this.attemptedTotal : this.stats.total;
        },
        isMistakePractice() {
            return this.practiceMode === 'mistakes';
        },
        mistakePracticeWords() {
            const wordsByKey = new Map();
            this.words.forEach((word) => {
                const key = this.wordKey(word.word);
                if (key && !wordsByKey.has(key)) {
                    wordsByKey.set(key, this.cloneWord(word));
                }
            });

            const reviewWords = [];
            const seen = new Set();
            this.stats.errors.forEach((error) => {
                const source = error.wordData || wordsByKey.get(this.wordKey(error.word)) || {
                    word: error.word,
                    chinese_meaning: error.meaning
                };
                const word = this.cloneWord(source);
                const key = this.wordKey(word.word);
                if (!key || seen.has(key)) {
                    return;
                }
                seen.add(key);
                reviewWords.push(word);
            });
            return reviewWords;
        },
        cardClass() {
            if (this.isAdvancing) {
                return this.stealthMode
                    ? 'practice-card-success practice-card-success-muted border-2 border-gray-500'
                    : 'practice-card-success border-2 border-green-400';
            }
            if (this.showAnswer) {
                if (this.stealthMode) {
                    return this.isCorrect ? 'border-2 border-gray-500' : 'border-2 border-gray-600';
                }
                return this.isCorrect ? 'border-4 border-green-500' : 'border-4 border-red-500';
            }
            return '';
        },
        inputClass() {
            if (this.isAdvancing) {
                return this.stealthMode ? 'border-gray-500 bg-gray-50 practice-input-success' : 'border-green-500 bg-green-50 practice-input-success';
            }
            if (this.showAnswer) {
                if (this.stealthMode) {
                    return this.isCorrect ? 'border-gray-500 bg-gray-50' : 'border-gray-600 bg-gray-100';
                }
                return this.isCorrect ? 'border-green-500 bg-green-50' : 'border-red-500 bg-red-50';
            }
            return 'border-gray-300';
        },
        feedbackClass() {
            if (this.stealthMode) {
                return this.isCorrect ? 'text-gray-700' : 'text-gray-800';
            }
            return this.isCorrect ? 'text-green-600' : 'text-red-600';
        }
    },
    watch: {
        userInput(newVal) {
            if (this.isRestoringDraft) {
                return;
            }

            const filtered = this.sanitizeInput(newVal);
            if (filtered !== newVal) {
                this.$nextTick(() => {
                    this.userInput = filtered;
                });
                return;
            }

            this.scheduleDraftSave();
        }
    },
    methods: {
        sanitizeInput(value) {
            return String(value || '').replace(/[^a-zA-Z\s'-]/g, '').replace(/\s+/g, ' ');
        },

        isValidAnswerInput(value) {
            const normalized = this.sanitizeInput(value).trim();
            return /^[a-zA-Z][a-zA-Z\s'-]*$/.test(normalized);
        },

        wordKey(value) {
            return this.normalizeAnswer(value);
        },

        cloneWord(word) {
            const source = word || {};
            return {
                id: source.id || 0,
                word: String(source.word || ''),
                chinese_meaning: String(source.chinese_meaning || source.meaning || ''),
                part_of_speech: String(source.part_of_speech || ''),
                phonetic: String(source.phonetic || ''),
                example_en: String(source.example_en || ''),
                example_cn: String(source.example_cn || ''),
                category: String(source.category || '')
            };
        },

        handleBeforeInput(event) {
            if (!event.data) {
                return;
            }
            if (this.showAnswer || this.isAdvancing) {
                event.preventDefault();
                return;
            }
            if (this.sanitizeInput(event.data) !== event.data) {
                event.preventDefault();
            }
        },

        handleInput() {
            const filtered = this.sanitizeInput(this.userInput);
            if (filtered !== this.userInput) {
                this.userInput = filtered;
            }
        },

        handleCompositionStart() {
            this.isComposing = true;
        },

        handleCompositionEnd() {
            this.isComposing = false;
            this.handleInput();
            this.scheduleDraftSave();
        },

        async fetchWords({ clearDraft = true } = {}) {
            if (clearDraft) {
                this.clearDraftSession();
            }

            this.isLoadingWords = true;
            this.wordsError = '';
            this.words = [];
            this.resetPracticeSession();

            try {
                const response = await axios.get(`${this.apiBaseUrl}/words`, {
                    params: { limit: 20 }
                });

                if (response.data.success) {
                    this.words = Array.isArray(response.data.data) ? response.data.data : [];
                    this.initializePracticeSession();
                } else {
                    this.wordsError = response.data.error || '获取单词失败';
                }
            } catch (error) {
                console.error('Error fetching words:', error);
                this.wordsError = error.response?.data?.error || '无法连接后端服务';
            } finally {
                this.isLoadingWords = false;
            }
        },

        async openSyncModal() {
            this.syncModal.visible = true;
            await this.loadSyncStatus();
        },

        closeSyncModal() {
            this.syncModal.visible = false;
        },

        async loadSyncStatus() {
            this.syncModal.loading = true;
            this.syncModal.error = '';
            try {
                const response = await axios.get(`${this.apiBaseUrl}/sync/status`);
                this.syncModal.status = response.data.data || null;
            } catch (error) {
                console.error('Error loading sync status:', error);
                this.syncModal.error = this.stealthMode ? 'Unable to load sync status' : '无法加载同步状态';
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
                await this.fetchWords();
            } catch (error) {
                console.error('Error syncing Anki collection:', error);
                const message = error.response?.data?.error || (this.stealthMode ? 'Sync failed' : '同步失败');
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
                return this.stealthMode ? 'Never' : '暂无';
            }
            return new Date(value).toLocaleString('zh-CN', {
                hour12: false,
                timeZone: 'Asia/Shanghai'
            });
        },

        syncHistory() {
            return (this.syncModal.status && this.syncModal.status.history) || [];
        },

        initializePracticeSession() {
            this.sessionId = this.generateSessionId();
            this.sessionStartedAt = new Date();
            this.currentIndex = 0;
            this.isFinished = false;
            this.isPracticeAbandoned = false;
            this.stats = {
                total: this.words.length,
                correct: 0,
                incorrect: 0,
                errors: [],
                attempts: []
            };
            this.resetInputState();
            this.beginCurrentWord();
            this.focusInput();
            this.saveDraftSession();
        },

        resetPracticeSession() {
            this.sessionId = '';
            this.sessionStartedAt = null;
            this.currentIndex = 0;
            this.isFinished = false;
            this.isPracticeAbandoned = false;
            this.practiceMode = 'normal';
            this.currentWordStartedAt = 0;
            this.stats = {
                total: 0,
                correct: 0,
                incorrect: 0,
                errors: [],
                attempts: []
            };
            this.resetInputState();
        },

        restoreDraftSession() {
            const rawDraft = localStorage.getItem(this.draftStorageKey);
            if (!rawDraft) {
                return false;
            }

            let draft = null;
            try {
                draft = JSON.parse(rawDraft);
            } catch (error) {
                console.warn('Invalid draft session:', error);
                this.clearDraftSession();
                return false;
            }

            if (!this.isValidDraftSession(draft)) {
                this.clearDraftSession();
                return false;
            }

            const elapsedSeconds = Math.max(Number(draft.currentWordElapsedSeconds || 0), 0);
            const showAnswer = Boolean(draft.showAnswer) && !Boolean(draft.isCorrect);

            this.clearAdvanceTimer();
            this.isRestoringDraft = true;
            this.words = draft.words;
            this.currentIndex = Math.min(Math.max(Number(draft.currentIndex || 0), 0), this.words.length);
            this.userInput = this.sanitizeInput(draft.userInput || '');
            this.isChecking = false;
            this.showAnswer = showAnswer;
            this.isCorrect = false;
            this.feedbackMessage = showAnswer ? String(draft.feedbackMessage || '✗ 错误') : '';
            this.isFinished = false;
            this.isPracticeAbandoned = false;
            this.isLoadingWords = false;
            this.isAdvancing = false;
            this.wordsError = '';
            this.practiceMode = this.normalizePracticeMode(draft.practiceMode);
            this.sessionId = draft.sessionId;
            this.sessionStartedAt = this.parseDraftDate(draft.sessionStartedAt) || new Date();
            this.currentWordStartedAt = performance.now() - elapsedSeconds * 1000;
            this.stats = this.normalizeDraftStats(draft.stats);
            this.isRestoringDraft = false;
            if (this.currentIndex >= this.words.length) {
                this.finishPractice();
                return true;
            }
            this.focusInput();
            return true;
        },

        isValidDraftSession(draft) {
            if (!draft || draft.version !== 1) return false;
            if (!Array.isArray(draft.words) || draft.words.length === 0) return false;
            if (!draft.sessionId || typeof draft.sessionId !== 'string') return false;
            if (!this.parseDraftDate(draft.sessionStartedAt)) return false;

            const currentIndex = Number(draft.currentIndex);
            if (!Number.isInteger(currentIndex) || currentIndex < 0 || currentIndex > draft.words.length) {
                return false;
            }

            const savedAt = this.parseDraftDate(draft.savedAt);
            if (!savedAt) return false;

            const maxAgeMs = 7 * 24 * 60 * 60 * 1000;
            return Date.now() - savedAt.getTime() <= maxAgeMs;
        },

        parseDraftDate(value) {
            const date = new Date(value);
            return Number.isNaN(date.getTime()) ? null : date;
        },

        normalizeDraftStats(stats) {
            const source = stats || {};
            return {
                total: Number(source.total || this.words.length),
                correct: Number(source.correct || 0),
                incorrect: Number(source.incorrect || 0),
                errors: Array.isArray(source.errors) ? source.errors : [],
                attempts: Array.isArray(source.attempts) ? source.attempts : []
            };
        },

        normalizePracticeMode(value) {
            return value === 'mistakes' ? 'mistakes' : 'normal';
        },

        scheduleDraftSave() {
            if (this.isRestoringDraft || this.isFinished || this.isAdvancing || !this.words.length || !this.sessionId) {
                return;
            }

            if (this.draftSaveTimer) {
                window.clearTimeout(this.draftSaveTimer);
            }

            this.draftSaveTimer = window.setTimeout(() => {
                this.draftSaveTimer = null;
                this.saveDraftSession();
            }, 250);
        },

        saveDraftSession(overrides = {}) {
            if (this.isRestoringDraft || this.isFinished || this.isAdvancing || !this.words.length || !this.sessionId) {
                return;
            }

            const draft = {
                version: 1,
                savedAt: new Date().toISOString(),
                words: this.words,
                currentIndex: overrides.currentIndex ?? this.currentIndex,
                userInput: overrides.userInput ?? this.userInput,
                showAnswer: overrides.showAnswer ?? this.showAnswer,
                isCorrect: overrides.isCorrect ?? this.isCorrect,
                feedbackMessage: overrides.feedbackMessage ?? this.feedbackMessage,
                practiceMode: this.practiceMode,
                sessionId: this.sessionId,
                sessionStartedAt: this.sessionStartedAt ? this.sessionStartedAt.toISOString() : new Date().toISOString(),
                currentWordElapsedSeconds: overrides.currentWordElapsedSeconds ?? (this.getCurrentWordTimeSpent() || 0),
                stats: this.stats
            };

            try {
                localStorage.setItem(this.draftStorageKey, JSON.stringify(draft));
            } catch (error) {
                console.warn('Unable to save draft session:', error);
            }
        },

        clearDraftSession() {
            if (this.draftSaveTimer) {
                window.clearTimeout(this.draftSaveTimer);
                this.draftSaveTimer = null;
            }
            localStorage.removeItem(this.draftStorageKey);
        },

        saveCorrectAdvanceDraft() {
            const nextIndex = this.currentIndex + 1;
            if (nextIndex >= this.words.length) {
                this.saveDraftSession({
                    currentIndex: this.words.length,
                    userInput: '',
                    showAnswer: false,
                    isCorrect: false,
                    feedbackMessage: '',
                    currentWordElapsedSeconds: 0
                });
                return;
            }

            this.saveDraftSession({
                currentIndex: nextIndex,
                userInput: '',
                showAnswer: false,
                isCorrect: false,
                feedbackMessage: '',
                currentWordElapsedSeconds: 0
            });
        },

        beginCurrentWord() {
            this.currentWordStartedAt = performance.now();
        },

        getCurrentWordTimeSpent() {
            if (!this.currentWordStartedAt) {
                return null;
            }
            return Math.max((performance.now() - this.currentWordStartedAt) / 1000, 0);
        },

        handleKeydown(event) {
            if (this.isAdvancing) {
                event.preventDefault();
                return;
            }

            if (event.key === 'Enter') {
                this.handleEnter(event);
                return;
            }

            // 处理空格键：只有在输入框为空且未显示答案时才跳过
            if (event.key === ' ' || event.code === 'Space') {
                if (!this.userInput.trim() && !this.showAnswer) {
                    event.preventDefault();
                    this.skipWord();
                } else if (this.showAnswer) {
                    event.preventDefault();
                }
            }
        },

        handleEnter(event) {
            event.preventDefault();
            if (this.isComposing || this.isAdvancing) {
                return;
            }
            if (this.showAnswer) {
                this.nextWord();
                return;
            }
            this.submitAnswer();
        },

        submitAnswer() {
            const trimmedInput = this.sanitizeInput(this.userInput).trim();
            this.userInput = trimmedInput;
            if (!this.currentWord || !trimmedInput || this.isChecking || this.showAnswer || this.isAdvancing) {
                return;
            }

            if (!this.isValidAnswerInput(trimmedInput)) {
                return;
            }

            this.isChecking = true;
            const timeSpent = this.getCurrentWordTimeSpent();
            this.isCorrect = this.checkAnswerLocally();
            this.isChecking = false;

            this.updateStats(trimmedInput, timeSpent);
            if (this.isCorrect) {
                this.feedbackMessage = '';
                this.playSuccessAnimation();
                this.saveCorrectAdvanceDraft();
                this.startCorrectAdvance();
                return;
            }

            this.showAnswer = true;
            this.displayFeedback();
            this.focusInput();
            this.saveDraftSession();
        },

        checkAnswerLocally() {
            const input = this.normalizeAnswer(this.userInput);
            return this.answerCandidates(this.currentWord.word).includes(input);
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

        analyzeErrorType(expected, input) {
            const sanitizedInput = this.normalizeAnswer(input);
            const candidates = this.answerCandidates(expected);
            if (!sanitizedInput) return 'skipped';
            if (candidates.includes(sanitizedInput)) return '';

            const bestMatch = candidates.reduce((best, candidate) => {
                const distance = this.levenshteinDistance(candidate, sanitizedInput);
                if (!best || distance < best.distance) {
                    return { value: candidate, distance };
                }
                return best;
            }, null);

            if (!bestMatch) return 'completely_wrong';

            const distance = bestMatch.distance;
            if (distance === 1) {
                if (sanitizedInput.length < bestMatch.value.length) return 'missing_letter';
                if (sanitizedInput.length > bestMatch.value.length) return 'extra_letter';
                return 'spelling';
            }
            if (distance <= 3) return 'spelling';
            return 'completely_wrong';
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

        recordAttempt(userInput, isCorrect, timeSpent, errorType = '') {
            if (!this.currentWord) return;
            this.stats.attempts.push({
                word: this.currentWord.word,
                chinese_meaning: this.currentWord.chinese_meaning,
                category: this.currentWord.category || '',
                user_input: userInput,
                is_correct: isCorrect,
                time_spent: timeSpent,
                error_type: errorType
            });
        },

        updateStats(userInput, timeSpent) {
            if (this.isCorrect) {
                this.stats.correct++;
                this.recordAttempt(userInput, true, timeSpent, '');
            } else {
                const errorType = this.analyzeErrorType(this.currentWord.word, userInput);
                const wordData = this.cloneWord(this.currentWord);
                this.stats.incorrect++;
                this.stats.errors.push({
                    word: wordData.word,
                    meaning: wordData.chinese_meaning,
                    user_input: userInput,
                    wordData
                });
                this.recordAttempt(userInput, false, timeSpent, errorType);
            }
        },

        displayFeedback() {
            if (this.isCorrect) {
                this.feedbackMessage = '✓ 正确！';
                this.playSuccessAnimation();
            } else {
                this.feedbackMessage = '✗ 错误';
                this.playErrorAnimation();
            }
        },

        playSuccessAnimation() {
            if (navigator.vibrate) {
                navigator.vibrate(35);
            }
        },

        startCorrectAdvance() {
            this.isAdvancing = true;
            this.advanceTimer = window.setTimeout(() => {
                this.advanceTimer = null;
                if (this.isAdvancing && !this.isFinished) {
                    this.nextWord();
                }
            }, 180);
        },

        clearAdvanceTimer() {
            if (this.advanceTimer) {
                window.clearTimeout(this.advanceTimer);
                this.advanceTimer = null;
            }
            this.isAdvancing = false;
        },

        playErrorAnimation() {
            // 可以添加震动效果
            if (navigator.vibrate) {
                navigator.vibrate([100, 50, 100]);
            }
        },

        nextWord() {
            this.currentIndex++;

            if (this.currentIndex >= this.words.length) {
                this.finishPractice();
                return;
            }

            this.resetInputState();
            this.beginCurrentWord();
            this.focusInput();
            this.saveDraftSession();
        },

        skipWord() {
            if (this.showAnswer || this.isAdvancing || !this.currentWord) return;

            const timeSpent = this.getCurrentWordTimeSpent();
            const wordData = this.cloneWord(this.currentWord);
            this.stats.incorrect++;
            this.stats.errors.push({
                word: wordData.word,
                meaning: wordData.chinese_meaning,
                user_input: '(跳过)',
                wordData
            });
            this.recordAttempt('', false, timeSpent, 'skipped');

            this.nextWord();
        },

        resetInputState() {
            this.clearAdvanceTimer();
            this.userInput = '';
            this.isChecking = false;
            this.showAnswer = false;
            this.isCorrect = false;
            this.feedbackMessage = '';
        },

        focusInput() {
            this.$nextTick(() => {
                if (this.$refs.inputField) {
                    this.$refs.inputField.focus();
                }
            });
        },

        finishPractice({ submit = true, abandoned = false } = {}) {
            this.clearAdvanceTimer();
            this.isFinished = true;
            this.isPracticeAbandoned = abandoned;
            this.clearDraftSession();
            if (submit && !this.isMistakePractice) {
                this.submitStats();
            }
        },

        async submitStats() {
            const attemptedTotal = this.stats.correct + this.stats.incorrect;
            if (!attemptedTotal) {
                return;
            }

            const endedAt = new Date();
            const durationSeconds = this.sessionStartedAt
                ? Math.max(Math.round((endedAt - this.sessionStartedAt) / 1000), 0)
                : 0;

            try {
                await axios.post(`${this.apiBaseUrl}/stats/sessions`, {
                    session_id: this.sessionId,
                    start_time: this.sessionStartedAt.toISOString(),
                    end_time: endedAt.toISOString(),
                    total_words: attemptedTotal,
                    correct_words: this.stats.correct,
                    incorrect_words: this.stats.incorrect,
                    accuracy: (this.stats.correct * 100) / attemptedTotal,
                    duration_seconds: durationSeconds,
                    word_attempts: this.stats.attempts
                });
            } catch (error) {
                console.error('Error submitting stats:', error);
            }
        },

        generateSessionId() {
            return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
                const r = Math.random() * 16 | 0;
                const v = c === 'x' ? r : (r & 0x3 | 0x8);
                return v.toString(16);
            });
        },

        restartPractice() {
            this.clearDraftSession();
            this.fetchWords();
        },

        startMistakePractice() {
            const reviewWords = this.mistakePracticeWords;
            if (!reviewWords.length) {
                return;
            }

            this.clearDraftSession();
            this.words = reviewWords;
            this.practiceMode = 'mistakes';
            this.initializePracticeSession();
        },

        quitPractice() {
            const message = this.stealthMode ? 'Exit practice?' : '确定要退出练习吗？';
            if (confirm(message)) {
                this.finishPractice({ submit: false, abandoned: true });
            }
        },

        toggleStealthMode() {
            this.stealthMode = !this.stealthMode;
            // 保存到 localStorage
            localStorage.setItem('stealthMode', this.stealthMode);
        },

        loadStealthMode() {
            const saved = localStorage.getItem('stealthMode');
            if (saved !== null) {
                this.stealthMode = saved === 'true';
            }
        },

        showError(message) {
            alert(message);
        }
    },
    mounted() {
        this.loadStealthMode();
        if (!this.restoreDraftSession()) {
            this.fetchWords();
        }
        this.focusInput();

        // 添加全局键盘事件监听
        window.addEventListener('keydown', (e) => {
            // 防止空格键滚动页面
            if (e.code === 'Space' && e.target === document.body) {
                e.preventDefault();
            }
            // 输入框在提交时会短暂 disabled，浏览器可能把焦点丢到 body。
            // 这里做兜底：显示答案后，即使焦点不在输入框，Enter 也能进入下一题。
            if (e.key === 'Enter' && this.showAnswer && e.target === document.body) {
                this.handleEnter(e);
            }
        });

        window.addEventListener('beforeunload', () => {
            this.saveDraftSession();
        });
    }
}).mount('#app');

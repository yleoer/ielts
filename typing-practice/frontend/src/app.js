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
            advanceTimer: null,
            wordsError: '',
            sessionId: '',
            sessionStartedAt: null,
            currentWordStartedAt: 0,
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
            const filtered = this.sanitizeInput(newVal);
            if (filtered !== newVal) {
                this.$nextTick(() => {
                    this.userInput = filtered;
                });
            }
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
        },

        async fetchWords() {
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
        },

        resetPracticeSession() {
            this.sessionId = '';
            this.sessionStartedAt = null;
            this.currentIndex = 0;
            this.isFinished = false;
            this.isPracticeAbandoned = false;
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
                this.startCorrectAdvance();
                return;
            }

            this.showAnswer = true;
            this.displayFeedback();
            this.focusInput();
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
                this.stats.incorrect++;
                this.stats.errors.push({
                    word: this.currentWord.word,
                    meaning: this.currentWord.chinese_meaning,
                    user_input: userInput
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
        },

        skipWord() {
            if (this.showAnswer || this.isAdvancing || !this.currentWord) return;

            const timeSpent = this.getCurrentWordTimeSpent();
            this.stats.incorrect++;
            this.stats.errors.push({
                word: this.currentWord.word,
                meaning: this.currentWord.chinese_meaning,
                user_input: '(跳过)'
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
            if (submit) {
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
            this.fetchWords();
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
        this.fetchWords();
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
    }
}).mount('#app');

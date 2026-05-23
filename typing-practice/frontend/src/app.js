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
            isComposing: false,
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
            return ((this.currentIndex + 1) / this.words.length) * 100;
        },
        accuracy() {
            if (this.stats.total === 0) return 0;
            return Math.round((this.stats.correct / this.stats.total) * 100);
        },
        cardClass() {
            if (this.showAnswer) {
                if (this.stealthMode) {
                    return this.isCorrect ? 'border-2 border-gray-500' : 'border-2 border-gray-600';
                }
                return this.isCorrect ? 'border-4 border-green-500' : 'border-4 border-red-500';
            }
            return '';
        },
        inputClass() {
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
            if (!event.data || this.showAnswer) {
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
            try {
                const response = await axios.get(`${this.apiBaseUrl}/words`, {
                    params: { limit: 20 }
                });

                if (response.data.success) {
                    this.words = response.data.data;
                    this.initializePracticeSession();
                } else {
                    this.showError('获取单词失败');
                }
            } catch (error) {
                console.error('Error fetching words:', error);
                // 使用模拟数据进行开发测试
                this.loadMockData();
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

        loadMockData() {
            // 模拟数据，用于前端开发测试
            this.words = [
                {
                    id: 1,
                    word: 'atmosphere',
                    phonetic: '/ˈætməsfɪə(r)/',
                    part_of_speech: 'n.',
                    chinese_meaning: '大气层；氛围'
                },
                {
                    id: 2,
                    word: 'catastrophic',
                    phonetic: '/ˌkætəˈstrɒfɪk/',
                    part_of_speech: 'adj.',
                    chinese_meaning: '灾难性的'
                },
                {
                    id: 3,
                    word: 'phenomenon',
                    phonetic: '/fəˈnɒmɪnən/',
                    part_of_speech: 'n.',
                    chinese_meaning: '现象'
                },
                {
                    id: 4,
                    word: 'longitude',
                    phonetic: '/ˈlɒŋɡɪtjuːd/',
                    part_of_speech: 'n.',
                    chinese_meaning: '经度'
                },
                {
                    id: 5,
                    word: 'humanitarian',
                    phonetic: '/hjuːˌmænɪˈteəriən/',
                    part_of_speech: 'adj./n.',
                    chinese_meaning: '人道主义的；人道主义者'
                }
            ];
            this.initializePracticeSession();
            console.log('使用模拟数据进行测试');
        },

        initializePracticeSession() {
            this.sessionId = this.generateSessionId();
            this.sessionStartedAt = new Date();
            this.currentIndex = 0;
            this.isFinished = false;
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
            if (this.isComposing) {
                return;
            }
            if (this.showAnswer) {
                this.nextWord();
                return;
            }
            this.submitAnswer();
        },

        async submitAnswer() {
            const trimmedInput = this.sanitizeInput(this.userInput).trim();
            this.userInput = trimmedInput;
            if (!trimmedInput || this.isChecking || this.showAnswer) {
                return;
            }

            if (!this.isValidAnswerInput(trimmedInput)) {
                return;
            }

            this.isChecking = true;
            const timeSpent = this.getCurrentWordTimeSpent();

            try {
                const response = await axios.post(`${this.apiBaseUrl}/check`, {
                    word_id: this.currentWord.id,
                    user_input: trimmedInput
                });

                this.isCorrect = response.data.correct;
            } catch (error) {
                console.error('Error checking answer:', error);
                // 本地检查逻辑（后端不可用时）
                this.isCorrect = this.checkAnswerLocally();
            } finally {
                this.isChecking = false;
            }

            this.showAnswer = true;
            this.updateStats(trimmedInput, timeSpent);
            this.displayFeedback();
            this.focusInput();

            if (this.isCorrect) {
                window.setTimeout(() => {
                    if (this.showAnswer && this.isCorrect && !this.isFinished) {
                        this.nextWord();
                    }
                }, 350);
            }
        },

        checkAnswerLocally() {
            const expected = this.currentWord.word.toLowerCase().trim();
            const input = this.userInput.toLowerCase().trim();
            return expected === input;
        },

        analyzeErrorType(expected, input) {
            const sanitizedInput = this.sanitizeInput(input).trim().toLowerCase();
            const sanitizedExpected = this.sanitizeInput(expected).trim().toLowerCase();
            if (!sanitizedInput) return 'skipped';
            if (sanitizedInput === sanitizedExpected) return '';

            const distance = this.levenshteinDistance(sanitizedExpected, sanitizedInput);
            if (distance === 1) {
                if (sanitizedInput.length < sanitizedExpected.length) return 'missing_letter';
                if (sanitizedInput.length > sanitizedExpected.length) return 'extra_letter';
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
            // 可以添加更复杂的动画效果
            if (navigator.vibrate) {
                navigator.vibrate(100);
            }
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
            if (this.showAnswer) return;

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

        finishPractice() {
            this.isFinished = true;
            this.submitStats();
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
                this.finishPractice();
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

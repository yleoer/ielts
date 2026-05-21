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
            stealthMode: false,
            stats: {
                total: 0,
                correct: 0,
                incorrect: 0,
                errors: []
            },
            apiBaseUrl: 'http://localhost:8080/api'
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
    methods: {
        async fetchWords() {
            try {
                const response = await axios.get(`${this.apiBaseUrl}/words`, {
                    params: { limit: 20 }
                });

                if (response.data.success) {
                    this.words = response.data.data;
                    this.stats.total = this.words.length;
                } else {
                    this.showError('获取单词失败');
                }
            } catch (error) {
                console.error('Error fetching words:', error);
                // 使用模拟数据进行开发测试
                this.loadMockData();
            }
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
            this.stats.total = this.words.length;
            console.log('使用模拟数据进行测试');
        },

        async submitAnswer() {
            if (!this.userInput.trim() || this.isChecking || this.showAnswer) {
                return;
            }

            this.isChecking = true;

            try {
                const response = await axios.post(`${this.apiBaseUrl}/check`, {
                    word_id: this.currentWord.id,
                    user_input: this.userInput.trim()
                });

                this.isCorrect = response.data.correct;
            } catch (error) {
                console.error('Error checking answer:', error);
                // 本地检查逻辑（后端不可用时）
                this.isCorrect = this.checkAnswerLocally();
            }

            this.showAnswer = true;
            this.updateStats();
            this.displayFeedback();

            // 移除自动跳转，改为手动点击或按 Enter
        },

        checkAnswerLocally() {
            const expected = this.currentWord.word.toLowerCase().trim();
            const input = this.userInput.toLowerCase().trim();
            return expected === input;
        },

        updateStats() {
            if (this.isCorrect) {
                this.stats.correct++;
            } else {
                this.stats.incorrect++;
                this.stats.errors.push({
                    word: this.currentWord.word,
                    meaning: this.currentWord.chinese_meaning,
                    user_input: this.userInput
                });
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
            this.focusInput();
        },

        skipWord() {
            if (this.showAnswer) return;

            this.stats.incorrect++;
            this.stats.errors.push({
                word: this.currentWord.word,
                meaning: this.currentWord.chinese_meaning,
                user_input: '(跳过)'
            });

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
            try {
                await axios.post(`${this.apiBaseUrl}/stats`, {
                    session_id: this.generateSessionId(),
                    total: this.stats.total,
                    correct: this.stats.correct,
                    duration_seconds: 0, // 可以添加计时功能
                    errors: this.stats.errors
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
            this.currentIndex = 0;
            this.isFinished = false;
            this.stats = {
                total: this.words.length,
                correct: 0,
                incorrect: 0,
                errors: []
            };
            this.resetInputState();
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
        });
    }
}).mount('#app');

const { createApp } = Vue;

createApp({
    data() {
        return {
            loading: true,
            loadError: false,
            overview: {},
            calendar: null,
            calendarLoading: false,
            calendarError: false,
            calendarFocusDate: '',
            optimization: { status: null, items: [], nextBeforeId: null, loading: false, error: '' },
            vocabulary: null,
            vocabularyLoading: false,
            vocabularyError: false,
            vocabularyFilters: [
                { value: 'all', label: '全部' }, { value: 'new', label: '未开始' },
                { value: 'learning', label: '学习中' }, { value: 'mastered', label: '已掌握' }
            ],
            today: new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date()),
            trendMonth: '',
            trendLoading: false,
            trendError: false,
            trendData: [],
            trendChart: null,
            detailModal: {
                visible: false,
                loading: false,
                title: '',
                subtitle: '',
                type: '',
                error: '',
                items: []
            },
            apiBaseUrl: window.location.origin && window.location.origin.startsWith('http')
                ? `${window.location.origin}/api`
                : 'http://localhost:8080/api'
        };
    },
    computed: {
        overviewCards() {
            const o = this.overview || {};
            const minutes = Number(o.total_time_minutes || 0);
            const time = minutes >= 60
                ? { value: (minutes / 60).toFixed(1), unit: '小时' }
                : { value: Math.round(minutes), unit: '分钟' };
            const totals = !this.vocabularyError && this.vocabulary?.overall;
            return [
                { label: '连续学习', value: o.current_streak || 0, unit: '天' },
                { label: '已学习', value: totals ? totals.learned : '—', unit: '词' },
                { label: '已掌握', value: totals ? totals.mastered : '—', unit: '词' },
                { label: '累计时长', value: time.value, unit: time.unit }
            ];
        },
        calendarWeeks() {
            return this.calendar ? this.buildCalendarWeeks(this.calendar) : [];
        },
        calendarMaxima() {
            const days = this.calendar?.days || [];
            return { practiced: Math.max(1, ...days.map(day => day.practiced)),
                due_count: Math.max(1, ...days.map(day => day.due_count)) };
        },
        calendarMonths() {
            const labels = [];
            const seen = new Set();
            this.calendarWeeks.forEach((week, index) => {
                const day = week.find(day => day && !seen.has(day.date.slice(0, 7)));
                if (day) {
                    const month = day.date.slice(0, 7);
                    seen.add(month);
                    labels.push({ month, label: `${Number(month.slice(5))}月`, column: index + 2,
                        current: month === this.today.slice(0, 7) });
                }
            });
            return labels;
        },
        calendarActiveDays() {
            return this.calendar?.days.filter(day => day.practiced > 0).length || 0;
        },
        calendarRangeLabel() {
            return this.calendar ? `${this.calendar.start_date.slice(0, 7).replace('-', '.')} — ${this.calendar.end_date.slice(0, 7).replace('-', '.')}` : '';
        },
        monthLabel() {
            const [year, month] = (this.trendMonth || this.today.slice(0, 7)).split('-');
            return `${year} 年 ${Number(month)} 月`;
        },
        trendEmpty() {
            return !this.trendData.some(item => item.words > 0);
        }
    },
    mounted() {
        this.updatePageAppearance();
        this.loadAllData();

        window.addEventListener('resize', () => {
            if (this.trendChart) {
                this.trendChart.resize();
            }
            // 热力图是纯 CSS 网格，自适应无需重绘。
        });
        window.addEventListener('keydown', (event) => {
            if (event.key === 'Escape' && this.detailModal.visible) {
                this.closeDetailModal();
            }
            if (event.key === 'Tab' && this.detailModal.visible) {
                const nodes = [...document.querySelectorAll('.detail-dialog button:not(:disabled), .detail-dialog [tabindex="0"]')];
                const first = nodes[0], last = nodes[nodes.length - 1];
                if (event.shiftKey && document.activeElement === first) {
                    event.preventDefault(); last?.focus();
                } else if (!event.shiftKey && document.activeElement === last) {
                    event.preventDefault(); first?.focus();
                }
            }
        });
    },
    methods: {
        updatePageAppearance() {
            document.title = '词间 · 统计';
            document.documentElement.lang = 'zh-CN';
        },

        async loadAllData() {
            this.loading = true;
            this.loadError = false;
            try {
                const response = await axios.get(`${this.apiBaseUrl}/stats/overview`);
                this.overview = response.data.data || {};
            } catch (error) {
                console.error('Error loading overview:', error);
                this.loading = false;
                this.loadError = true;
                return;
            }

            this.loading = false;
            await this.$nextTick();
            await Promise.allSettled([this.loadCalendar(), this.loadTrend(), this.loadVocabulary()]);
        },

        async loadCalendar() {
            this.calendarLoading = true;
            this.calendarError = false;
            try {
                const response = await axios.get(`${this.apiBaseUrl}/stats/calendar`);
                this.calendar = response.data.data;
                this.today = this.calendar.today;
                this.calendarFocusDate = this.today;
            } catch (error) {
                this.calendarError = true;
            } finally {
                this.calendarLoading = false;
            }
            await this.$nextTick();
            this.centerCalendar();
        },

        async loadTrend() {
            this.trendLoading = true;
            this.trendError = false;
            try {
                const response = await axios.get(`${this.apiBaseUrl}/stats/monthly-activity`);
                this.trendMonth = response.data.data.month;
                this.trendData = response.data.data.days;
            } catch (error) {
                this.trendError = true;
            } finally {
                this.trendLoading = false;
            }
            await this.$nextTick();
            this.renderTrend();
        },

        onOptimizationToggle(event) {
            if (event.target.open && !this.optimization.status) this.loadOptimization();
        },

        async loadOptimization(append = false) {
            const state = this.optimization;
            if (state.loading || (append && !state.nextBeforeId)) return;
            state.loading = true;
            state.error = '';
            try {
                const params = { limit: 10, before_id: append ? state.nextBeforeId : 0 };
                const [status, history] = await Promise.all([
                    axios.get(`${this.apiBaseUrl}/memory/optimization`),
                    axios.get(`${this.apiBaseUrl}/memory/optimization/runs`, { params })
                ]);
                state.status = status.data.data;
                state.items = append ? [...state.items, ...history.data.data.items] : history.data.data.items;
                state.nextBeforeId = history.data.data.next_before_id;
            } catch (error) {
                state.error = '无法加载参数优化记录，请检查连接后重试。';
            } finally {
                state.loading = false;
            }
        },

        optimizationSummary(status) {
            if (!status.enabled) return '自动优化已关闭';
            if (status.running_run_id) return '正在后台训练与验证，完成后将保存结果。';
            if (status.effective_reviews < status.minimum_reviews) {
                return `已积累 ${status.effective_reviews} / ${status.minimum_reviews} 条有效间隔复习，达到门槛后自动评估。`;
            }
            return status.next_evaluation_at ? `下次评估：${this.formatDue(status.next_evaluation_at)}` : '已达到门槛，等待后台评估。';
        },

        optimizationOutcome(status) {
            return { running: '评估中', accepted: '已启用', rejected: '保留现用参数', skipped: '已跳过',
                failed: '评估失败', interrupted: '任务中断', superseded: '配置已变更' }[status] || status;
        },

        formatMetric(value) {
            return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(4) : '—';
        },

        formatDue(value) {
            return value ? new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) : '尚未安排';
        },

        async loadVocabulary() {
            this.vocabularyLoading = true;
            this.vocabularyError = false;
            try {
                const response = await axios.get(`${this.apiBaseUrl}/stats/vocabulary-progress`);
                this.vocabulary = response.data.data;
            } catch (error) {
                this.vocabularyError = true;
            } finally {
                this.vocabularyLoading = false;
            }
        },

        progressPercent(group, key) {
            return group.total ? group[key] / group.total * 100 : 0;
        },

        progressDescription(group) {
            return `${group.value}：学习中 ${group.learning} 个，已掌握 ${group.mastered} 个，总单词数 ${group.total} 个`;
        },

        progressCounts(group) {
            return `${group.learning} / ${group.mastered} / ${group.total}`;
        },

        memoryLabel(status) {
            return { new: '未开始', learning: '学习中', mastered: '已掌握' }[status] || '';
        },

        highlightInput(expected, input) {
            const raw = Array.from(String(input || ''));
            const tokens = [];
            raw.forEach((text, index) => {
                if (/^[a-z'-]$/i.test(text)) tokens.push({ text: text.toLowerCase(), index });
                else if (/\s/.test(text) && tokens.length && tokens[tokens.length - 1].text !== ' ') {
                    tokens.push({ text: ' ', index });
                }
            });
            if (tokens[tokens.length - 1]?.text === ' ') tokens.pop();
            if (!tokens.length) return raw.map(text => ({ text, kind: 'wrong', description: '无效输入' }));
            const actual = tokens.map(token => token.text).join('');
            const normalize = value => value.replace(/[^a-zA-Z\s'-]/g, '').replace(/\s+/g, ' ').trim().toLowerCase();
            const candidates = String(expected || '').split('/').map(normalize).filter(Boolean);
            let best;
            for (const word of candidates.length ? candidates : ['']) {
                const matrix = Array.from({ length: word.length + 1 }, (_, i) =>
                    Array.from({ length: actual.length + 1 }, (_, j) => i ? (j ? 0 : i) : j));
                for (let i = 1; i <= word.length; i++) {
                    for (let j = 1; j <= actual.length; j++) {
                        matrix[i][j] = Math.min(matrix[i - 1][j] + 1, matrix[i][j - 1] + 1,
                            matrix[i - 1][j - 1] + (word[i - 1] === actual[j - 1] ? 0 : 1));
                    }
                }
                const distance = matrix[word.length][actual.length];
                if (!best || distance < best.distance) best = { word, matrix, distance };
            }
            const changes = new Map(), gaps = new Map();
            let i = best.word.length, j = actual.length;
            while (i || j) {
                if (i && j && best.word[i - 1] === actual[j - 1] && best.matrix[i][j] === best.matrix[i - 1][j - 1]) {
                    changes.set(tokens[j - 1].index, 'match'); i--; j--;
                } else if (i && j && best.matrix[i][j] === best.matrix[i - 1][j - 1] + 1) {
                    changes.set(tokens[j - 1].index, 'wrong'); i--; j--;
                } else if (i && best.matrix[i][j] === best.matrix[i - 1][j] + 1) {
                    const boundary = j < tokens.length ? tokens[j].index : tokens[j - 1].index + 1;
                    gaps.set(boundary, (gaps.get(boundary) || 0) + 1); i--;
                } else {
                    changes.set(tokens[j - 1].index, 'extra'); j--;
                }
            }
            const result = [];
            const descriptions = { match: '', wrong: '拼写错误', extra: '多写字符' };
            for (let index = 0; index <= raw.length; index++) {
                for (let gap = 0; gap < (gaps.get(index) || 0); gap++) {
                    result.push({ text: '□', kind: 'missing', description: '此处漏写一个字符' });
                }
                if (index < raw.length) {
                    const kind = changes.get(index) || 'match';
                    result.push({ text: raw[index], kind, description: descriptions[kind] });
                }
            }
            return result;
        },

        toggleWordErrors(item) {
            if (!item.total_attempts) return;
            if (!item.errorHistory) {
                item.errorHistory = { expanded: false, loaded: false, loading: false, error: '',
                    items: [], nextBeforeId: null, retryAppend: false };
            }
            const history = item.errorHistory;
            history.expanded = !history.expanded;
            if (history.expanded && !history.loaded && !history.loading) return this.loadWordErrors(item);
        },

        async loadWordErrors(item, append = false) {
            const history = item.errorHistory;
            if (history.loading || (append && history.nextBeforeId == null)) return;
            history.loading = true;
            history.error = '';
            try {
                const response = await axios.get(`${this.apiBaseUrl}/stats/word-errors`, {
                    params: { source_id: item.source_id, before_id: append ? history.nextBeforeId : 0, limit: 50 }
                });
                const data = response.data.data;
                const records = data.items.map(record => ({ ...record,
                    inputSegments: this.highlightInput(record.word, record.user_input) }));
                history.items = append ? [...history.items, ...records] : records;
                history.nextBeforeId = data.next_before_id;
                history.loaded = true;
                item.correct_attempts = data.correct_attempts;
                item.total_attempts = data.total_attempts;
            } catch (error) {
                history.error = '无法加载答错记录，请检查连接后重试。';
                history.retryAppend = append;
            } finally {
                history.loading = false;
            }
        },

        renderTrend() {
            const container = document.getElementById('trend-chart');
            if (!container || typeof echarts === 'undefined' || this.trendEmpty) {
                return;
            }
            if (!this.trendChart || this.trendChart.isDisposed()) {
                // ECharts owns a mutable object graph; Vue proxies break resize layout.
                this.trendChart = Vue.markRaw(echarts.init(container));
            }

            const barColor = '#c8d5cc';
            const lineColor = '#375d4c';
            const dates = this.trendData.map(item => String(Number(item.date.slice(8))));

            this.trendChart.setOption({
                animation: false,
                grid: { left: 40, right: 44, top: 16, bottom: 28 },
                tooltip: {
                    trigger: 'axis',
                    axisPointer: { type: 'shadow' },
                    formatter: (params) => {
                        const item = this.trendData[params[0].dataIndex];
                        if (!item.words) {
                            return `${item.date}<br/>未练习`;
                        }
                        return `${item.date}<br/>作答: ${item.words} 次<br/>正确率: ${item.accuracy.toFixed(1)}%`;
                    }
                },
                xAxis: {
                    type: 'category',
                    data: dates,
                    axisTick: { show: false },
                    axisLine: { lineStyle: { color: '#e5e7eb' } },
                    axisLabel: { color: '#5f6b62', fontSize: 12, interval: 4 }
                },
                yAxis: [
                    {
                        type: 'value',
                        minInterval: 1,
                        splitLine: { lineStyle: { color: '#f3f4f6' } },
                        axisLabel: { color: '#626b77', fontSize: 12 }
                    },
                    {
                        type: 'value',
                        min: 0,
                        max: 100,
                        interval: 25,
                        splitLine: { show: false },
                        axisLabel: { color: '#626b77', fontSize: 12, formatter: '{value}%' }
                    }
                ],
                series: [
                    {
                        name: '作答次数',
                        type: 'bar',
                        data: this.trendData.map((item) => item.words),
                        barMaxWidth: 14,
                        itemStyle: { color: barColor, borderRadius: [3, 3, 0, 0] }
                    },
                    {
                        name: '正确率',
                        type: 'line',
                        yAxisIndex: 1,
                        data: this.trendData.map((item) => item.accuracy),
                        connectNulls: false,
                        symbol: 'circle',
                        symbolSize: 5,
                        lineStyle: { width: 2, color: lineColor },
                        itemStyle: { color: lineColor }
                    }
                ]
            }, true);
        },

        buildCalendarWeeks(calendar) {
            const byDate = new Map(calendar.days.map(day => [day.date, day]));
            const start = new Date(calendar.start_date + 'T00:00:00Z');
            start.setUTCDate(start.getUTCDate() - start.getUTCDay());
            const end = new Date(calendar.end_date + 'T00:00:00Z');
            end.setUTCDate(end.getUTCDate() + 6 - end.getUTCDay());
            const weeks = [];
            for (let cursor = new Date(start); cursor <= end;) {
                const week = [];
                for (let index = 0; index < 7; index++) {
                    week.push(byDate.get(cursor.toISOString().slice(0, 10)) || null);
                    cursor.setUTCDate(cursor.getUTCDate() + 1);
                }
                weeks.push(week);
            }
            return weeks;
        },

        calendarDayClass(day) {
            const field = day.practiced ? 'practiced' : 'due_count';
            const max = this.calendarMaxima[field];
            return [day.practiced ? `calendar-history-${this.calendarLevel(day.practiced, max)}`
                : `calendar-due-${this.calendarLevel(day.due_count, max)}`,
                day.date === this.today ? 'calendar-today' : ''];
        },

        calendarDayDescription(day) {
            return `${day.date}：已学习 ${day.practiced} 个词，待复习 ${day.due_count} 个词`;
        },

        centerCalendar() {
            const scroll = this.$refs.calendarScroll;
            const today = scroll?.querySelector(`[data-date="${this.today}"]`);
            if (today && scroll.scrollWidth > scroll.clientWidth) {
                scroll.scrollLeft += today.getBoundingClientRect().left - scroll.getBoundingClientRect().left - scroll.clientWidth / 2;
            }
        },

        onCalendarKeydown(event, day) {
            const offsets = { ArrowDown: 1, ArrowUp: -1, ArrowRight: 7, ArrowLeft: -7 };
            const selected = new Date(day.date + 'T00:00:00Z');
            const offset = event.key === 'Home' ? -selected.getUTCDay()
                : event.key === 'End' ? 6 - selected.getUTCDay() : offsets[event.key];
            if (offset == null) return;
            event.preventDefault();
            selected.setUTCDate(selected.getUTCDate() + offset);
            const date = selected.toISOString().slice(0, 10);
            this.calendarFocusDate = date < this.calendar.start_date ? this.calendar.start_date
                : date > this.calendar.end_date ? this.calendar.end_date : date;
            this.$nextTick(() => this.$refs.calendarScroll.querySelector(`[data-date="${this.calendarFocusDate}"]`)?.focus());
        },

        calendarLevel(count, maxCount) {
            if (!count) return 0;
            if (maxCount <= 4) return Math.min(4, count);
            const ratio = count / maxCount;
            if (ratio <= 0.25) return 1;
            if (ratio <= 0.5) return 2;
            if (ratio <= 0.75) return 3;
            return 4;
        },

        closeDetailModal() {
            this.detailModal.visible = false;
            if (typeof document !== 'undefined') document.body.style.overflow = this.detailBodyOverflow || '';
            this.detailOpener?.focus();
        },

        beginDetail(values) {
            if (!this.detailModal.visible && typeof document !== 'undefined') {
                this.detailOpener = document.activeElement;
                this.detailBodyOverflow = document.body.style.overflow;
                document.body.style.overflow = 'hidden';
            }
            this.detailModal = { visible: true, loading: true, error: '', items: [], ...values };
            this.$nextTick?.(() => this.$refs.detailClose?.focus());
        },

        openCalendarWords(day) {
            this.beginDetail({ type: 'calendar', title: day.date,
                subtitle: '学习记录与复习安排', calendarDate: day.date,
                calendarMode: day.practiced ? 'practiced' : 'due',
                calendarGroups: { practiced: [], due: [] } });
            return this.loadCalendarWords();
        },

        async loadCalendarWords() {
            const modal = this.detailModal;
            modal.loading = true;
            modal.error = '';
            try {
                const response = await axios.get(`${this.apiBaseUrl}/stats/calendar-words`, { params: { date: modal.calendarDate } });
                modal.calendarGroups = response.data.data;
                modal.subtitle = `已学习 ${modal.calendarGroups.practiced.length} 个词 · 待复习 ${modal.calendarGroups.due.length} 个词`;
                if (!modal.calendarGroups[modal.calendarMode].length) {
                    modal.calendarMode = modal.calendarMode === 'practiced' ? 'due' : 'practiced';
                }
                modal.items = modal.calendarGroups[modal.calendarMode];
            } catch (error) {
                modal.error = '无法加载这一天的单词，请检查连接后重试。';
            } finally {
                modal.loading = false;
            }
        },

        selectCalendarMode(mode) {
            this.detailModal.calendarMode = mode;
            this.detailModal.items = this.detailModal.calendarGroups[mode];
        },

        openVocabularyWords(dimension, group) {
            if (!group.total) return;
            this.beginDetail({
                type: 'vocabulary', title: dimension === 'cefr' ? `${group.value} · ${group.label}` : group.label,
                subtitle: `学习中 / 已掌握 / 总单词数：${this.progressCounts(group)}`,
                dimension, value: group.value, status: 'all', nextOffset: null, total: 0
            });
            return this.loadVocabularyWords();
        },

        async loadVocabularyWords(append = false) {
            const modal = this.detailModal;
            if (append && (modal.loading || modal.nextOffset == null)) return;
            const request = (modal.request || 0) + 1;
            modal.request = request;
            modal.loading = true;
            modal.error = '';
            const offset = append ? modal.nextOffset : 0;
            if (!append) {
                modal.items = [];
                modal.nextOffset = null;
            }
            try {
                const response = await axios.get(`${this.apiBaseUrl}/stats/vocabulary-words`, {
                    params: { dimension: modal.dimension, value: modal.value, status: modal.status, offset, limit: 100 }
                });
                if (modal.request !== request) return;
                const data = response.data.data;
                modal.items = append ? [...modal.items, ...data.items] : data.items;
                modal.total = data.total;
                modal.nextOffset = data.next_offset;
            } catch (error) {
                if (modal.request === request) {
                    modal.error = '无法加载单词，请检查连接后重试。';
                    modal.retryAppend = append;
                }
            } finally {
                if (modal.request === request) modal.loading = false;
            }
        },

        selectVocabularyStatus(status) {
            this.detailModal.status = status;
            return this.loadVocabularyWords();
        }
    }
}).mount('#app');

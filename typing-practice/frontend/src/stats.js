const { createApp } = Vue;

// 掌握度依靠标签、数值与统一色阶呈现。
const MASTERY_LEVELS = [
    { key: 'mastered', zh: '已掌握', en: 'Mastered', color: '#375d4c' },
    { key: 'learning', zh: '学习中', en: 'Learning', color: '#a1b9a4' },
    { key: 'new', zh: '未开始', en: 'New', color: '#d4dfd1' }
];

const ERROR_TYPES = [
    { key: 'spelling', zh: '拼写错误', en: 'Typo' },
    { key: 'missing_letter', zh: '漏字母', en: 'Missing letter' },
    { key: 'extra_letter', zh: '多字母', en: 'Extra letter' },
    { key: 'completely_wrong', zh: '完全错误', en: 'Completely wrong' },
    { key: 'skipped', zh: '不会/跳过', en: 'Skipped' }
];

createApp({
    data() {
        return {
            loading: true,
            loadError: false,
            overview: {},
            memory: null,
            memoryLoading: false,
            memoryError: false,
            optimization: { status: null, items: [], nextBeforeId: null, loading: false, error: '' },
            mastery: null,
            masteryError: false,
            errorTypes: null,
            errorTypesError: false,
            heatmapData: [],
            heatmapYear: Number(new Intl.DateTimeFormat('en', { timeZone: 'Asia/Shanghai', year: 'numeric' }).format(new Date())),
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
                ? { value: (minutes / 60).toFixed(1), unit: this.t('小时', 'h') }
                : { value: Math.round(minutes), unit: this.t('分钟', 'min') };
            return [
                { label: this.t('累计练习单词', 'Words practiced'), value: o.total_words_practiced || 0, unit: '' },
                { label: this.t('整体正确率', 'Accuracy'), value: Number(o.overall_accuracy || 0).toFixed(1), unit: '%' },
                { label: this.t('连续学习', 'Streak'), value: o.current_streak || 0, unit: this.t('天', Number(o.current_streak) === 1 ? 'day' : 'days') },
                { label: this.t('累计时长', 'Total time'), value: time.value, unit: time.unit }
            ];
        },
        heatmapActiveDays() {
            return this.heatmapData.filter((item) => Number(item.words || 0) > 0).length;
        },
        trendEmpty() {
            return !this.trendData.some((item) => item.words > 0);
        },
        reviewForecast() {
            const days = this.memory?.due_forecast || [];
            const maxCount = Math.max(1, ...days.map((day) => day.count));
            return days.map((day, index) => {
                const [, month, date] = day.date.split('-');
                return {
                    ...day,
                    label: index === 0 ? '今天' : index === 1 ? '明天' : `${Number(month)}/${Number(date)}`,
                    barHeight: Math.max(3, day.count / maxCount * 40)
                };
            });
        },
        breakdownPanels() {
            return [this.masteryPanel(), this.errorTypePanel()];
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
        });
    },
    methods: {
        t(zh) {
            return zh;
        },

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

            // 各模块独立加载，单个失败不影响其它模块。
            await Promise.allSettled([
                this.loadHeatmap(),
                this.loadTrend(),
                this.loadMastery(),
                this.loadErrorTypes(),
                this.loadMemory()
            ]);

            this.loading = false;
            await this.$nextTick();
            this.renderHeatmap();
            this.renderTrend();
        },

        async loadHeatmap() {
            const year = this.heatmapYear;
            try {
                const response = await axios.get(`${this.apiBaseUrl}/stats/heatmap`, {
                    params: { start_date: `${year}-01-01`, end_date: `${year}-12-31` }
                });
                this.heatmapData = response.data.data || [];
            } catch (error) {
                console.warn('Failed to load heatmap', error);
                this.heatmapData = [];
            }
        },

        async loadTrend() {
            try {
                const response = await axios.get(`${this.apiBaseUrl}/stats/accuracy-trend`, { params: { days: 30 } });
                const byDate = new Map((response.data.data || []).map((item) => [item.date, item]));
                // 补齐没有练习的日期，x 轴是连续的 30 天，断档一目了然。
                this.trendData = this.lastNDays(30).map((date) => {
                    const item = byDate.get(date);
                    const words = item ? Number(item.total_words || 0) : 0;
                    return {
                        date,
                        words,
                        accuracy: words > 0 ? Number(item.accuracy || 0) : null
                    };
                });
            } catch (error) {
                console.warn('Failed to load trend', error);
                this.trendData = [];
            }
        },

        async loadMemory() {
            this.memoryLoading = true;
            this.memoryError = false;
            try {
                const response = await axios.get(`${this.apiBaseUrl}/memory/summary`);
                this.memory = response.data.data;
            } catch (error) {
                this.memoryError = true;
            } finally {
                this.memoryLoading = false;
            }
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

        async loadMastery() {
            try {
                const response = await axios.get(`${this.apiBaseUrl}/stats/mastery-distribution`);
                this.mastery = response.data.data || {};
                this.masteryError = false;
            } catch (error) {
                console.warn('Failed to load mastery', error);
                this.masteryError = true;
            }
        },

        async loadErrorTypes() {
            try {
                const response = await axios.get(`${this.apiBaseUrl}/stats/error-types`);
                this.errorTypes = response.data.data || {};
                this.errorTypesError = false;
            } catch (error) {
                console.warn('Failed to load error types', error);
                this.errorTypesError = true;
            }
        },

        lastNDays(days) {
            const result = [];
            const today = new Date(this.formatLocalDate(new Date()) + 'T00:00:00Z');
            for (let offset = days - 1; offset >= 0; offset--) {
                const d = new Date(today);
                d.setUTCDate(d.getUTCDate() - offset);
                result.push(d.toISOString().slice(0, 10));
            }
            return result;
        },

        formatLocalDate(d) {
            return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).format(d);
        },

        buildRows(defs, data, colorFor) {
            const total = defs.reduce((sum, def) => sum + Number(data[def.key] || 0), 0);
            const rows = defs.map((def) => {
                const value = Number(data[def.key] || 0);
                return {
                    key: def.key,
                    label: this.t(def.zh, def.en),
                    value,
                    percent: total ? Math.round((value * 1000) / total) / 10 : 0,
                    color: colorFor(def)
                };
            });
            return { rows, total };
        },

        masteryPanel() {
            const data = this.mastery || {};
            // 记忆状态按当前词池和 FSRS 卡片计算。
            const defs = MASTERY_LEVELS.filter((def) => def.key !== 'new' || Number(data.new || 0) > 0);
            const { rows, total } = this.buildRows(defs, data, (def) => def.color);
            return {
                key: 'mastery',
                title: this.t('单词记忆', 'Word memory'),
                totalText: `共 ${total} 个单词`,
                error: this.masteryError,
                total,
                rows,
                open: (row) => this.openMasteryWords(row.key, row.label, row.value)
            };
        },

        errorTypePanel() {
            const data = this.errorTypes || {};
            const color = '#a17764';
            const { rows, total } = this.buildRows(ERROR_TYPES, data, () => color);
            // 错误类型没有天然顺序，按次数从多到少排，最该关注的放最上面。
            rows.sort((a, b) => b.value - a.value);
            return {
                key: 'errors',
                title: this.t('错误类型', 'Error Types'),
                totalText: `共 ${total} 次`,
                error: this.errorTypesError,
                total,
                rows,
                open: (row) => this.openErrorTypeWords(row.key, row.label, row.value)
            };
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
            const dates = this.trendData.map((item) => item.date.slice(5));
            const t = this.t.bind(this);

            this.trendChart.setOption({
                animation: false,
                grid: { left: 40, right: 44, top: 16, bottom: 28 },
                tooltip: {
                    trigger: 'axis',
                    axisPointer: { type: 'shadow' },
                    formatter: (params) => {
                        const item = this.trendData[params[0].dataIndex];
                        if (!item.words) {
                            return `${item.date}<br/>${t('未练习', 'No practice')}`;
                        }
                        return `${item.date}<br/>${t('单词', 'Words')}: ${item.words}<br/>${t('正确率', 'Accuracy')}: ${item.accuracy.toFixed(1)}%`;
                    }
                },
                xAxis: {
                    type: 'category',
                    data: dates,
                    axisTick: { show: false },
                    axisLine: { lineStyle: { color: '#e5e7eb' } },
                    axisLabel: { color: '#626b77', fontSize: 12, interval: 6 }
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
                        name: t('单词', 'Words'),
                        type: 'bar',
                        data: this.trendData.map((item) => item.words),
                        barMaxWidth: 14,
                        itemStyle: { color: barColor, borderRadius: [3, 3, 0, 0] }
                    },
                    {
                        name: t('正确率', 'Accuracy'),
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

        renderHeatmap() {
            const container = document.getElementById('heatmap');
            if (!container) {
                return;
            }

            const year = this.heatmapYear;
            const countsByDate = new Map(this.heatmapData.map((item) => [
                item.date,
                { words: Number(item.words || 0), accuracy: Number(item.accuracy || 0) }
            ]));
            const maxWords = Math.max(0, ...this.heatmapData.map((item) => Number(item.words || 0)));
            const weeks = this.buildHeatmapWeeks(year);
            const monthLabels = this.buildHeatmapMonthLabels(year, weeks);
            const today = this.formatLocalDate(new Date());

            container.innerHTML = `
                <div class="github-heatmap">
                    <div class="github-heatmap-months" aria-hidden="true">
                        <span></span>
                        ${monthLabels.map((m) => `<span style="grid-column:${m.column};">${m.label}</span>`).join('')}
                    </div>
                    <div class="github-heatmap-body">
                        <div class="github-heatmap-weekdays" aria-hidden="true">
                            <span></span><span>${this.t('一', 'Mon')}</span><span></span>
                            <span>${this.t('三', 'Wed')}</span><span></span>
                            <span>${this.t('五', 'Fri')}</span><span></span>
                        </div>
                        <div class="github-heatmap-grid" role="img" aria-label="${this.t('学习日历', 'Practice calendar')}">
                    ${weeks.map((week) => `
                                <div class="github-heatmap-week">
                            ${week.map((date) => this.renderHeatmapCell(date, countsByDate, maxWords, year, today)).join('')}
                                </div>
                            `).join('')}
                        </div>
                    </div>
                    <div class="github-heatmap-legend">
                        <span>${this.t('少', 'Less')}</span>
                        ${[0, 1, 2, 3, 4].map((level) => `<span class="github-heatmap-cell github-heatmap-level-${level}"></span>`).join('')}
                        <span>${this.t('多', 'More')}</span>
                    </div>
                </div>
            `;
        },

        renderHeatmapCell(date, countsByDate, maxWords, year, today) {
            const dateText = date.toISOString().slice(0, 10);
            const inYear = date.getUTCFullYear() === year;
            const item = countsByDate.get(dateText) || { words: 0, accuracy: 0 };
            const level = inYear ? this.heatmapLevel(item.words, maxWords) : 0;
            const text = item.words
                ? this.t(`${dateText}：${item.words} 个单词，正确率 ${item.accuracy.toFixed(1)}%`,
                    `${dateText}: ${item.words} words, ${item.accuracy.toFixed(1)}% accuracy`)
                : this.t(`${dateText}：未练习`, `${dateText}: no practice`);
            const classes = [
                'github-heatmap-cell',
                `github-heatmap-level-${level}`,
                inYear ? '' : 'github-heatmap-outside',
                dateText === today ? 'github-heatmap-today' : ''
            ].filter(Boolean).join(' ');
            return `<span class="${classes}" title="${text}"></span>`;
        },

        buildHeatmapWeeks(year) {
            const start = new Date(Date.UTC(year, 0, 1));
            start.setUTCDate(start.getUTCDate() - start.getUTCDay());
            const end = new Date(Date.UTC(year, 11, 31));
            end.setUTCDate(end.getUTCDate() + (6 - end.getUTCDay()));

            const weeks = [];
            for (let cursor = new Date(start); cursor <= end; cursor.setUTCDate(cursor.getUTCDate() + 7)) {
                const week = [];
                for (let day = 0; day < 7; day++) {
                    const date = new Date(cursor);
                    date.setUTCDate(cursor.getUTCDate() + day);
                    week.push(date);
                }
                weeks.push(week);
            }
            return weeks;
        },

        buildHeatmapMonthLabels(year, weeks) {
            const names = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月'];
            const labels = [];
            const seen = new Set();
            weeks.forEach((week, index) => {
                const first = week.find((date) => date.getUTCFullYear() === year && date.getUTCDate() <= 7);
                if (first && !seen.has(first.getUTCMonth())) {
                    seen.add(first.getUTCMonth());
                    labels.push({ label: names[first.getUTCMonth()], column: index + 2 });
                }
            });
            return labels;
        },

        heatmapLevel(count, maxCount) {
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
        },

        async openDetail({ type, title, subtitle, url, params }) {
            this.detailModal = { visible: true, loading: true, title, subtitle, type, error: '', items: [] };
            const modal = this.detailModal;
            try {
                const response = await axios.get(`${this.apiBaseUrl}${url}`, { params });
                modal.items = response.data.data || [];
            } catch (error) {
                console.error('Error loading detail words:', error);
                modal.error = this.t('加载单词失败', 'Failed to load words');
            } finally {
                modal.loading = false;
            }
        },

        openForecastWords(day) {
            if (!day.count) return;
            return this.openDetail({
                type: 'forecast',
                title: `${day.label}待复习`,
                subtitle: `${day.date} · ${day.count} 个单词`,
                url: '/memory/forecast-words',
                params: { date: day.date }
            });
        },

        openMasteryWords(level, label, count) {
            return this.openDetail({
                type: 'mastery',
                title: label,
                subtitle: this.t(`${count || 0} 个单词`, `${count || 0} words`),
                url: '/stats/mastery-words',
                params: { level, limit: 500 }
            });
        },

        openErrorTypeWords(errorType, label, count) {
            return this.openDetail({
                type: 'error',
                title: label,
                subtitle: this.t(`${count || 0} 次错误`, `${count || 0} errors`),
                url: '/stats/error-type-words',
                params: { type: errorType, limit: 500 }
            });
        }
    }
}).mount('#app');

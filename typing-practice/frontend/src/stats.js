const { createApp } = Vue;

createApp({
    data() {
        return {
            loading: true,
            stealthMode: false,
            overview: {},
            charts: {},
            // 图表详情弹窗共用这一份状态：掌握度和错误类型点击后只切换 type/items。
            detailModal: {
                visible: false,
                loading: false,
                title: '',
                subtitle: '',
                type: '',
                items: []
            },
            apiBaseUrl: window.location.origin && window.location.origin.startsWith('http')
                ? `${window.location.origin}/api`
                : 'http://localhost:8080/api',
            useMockData: false
        };
    },
    mounted() {
        this.loadStealthMode();
        this.loadAllData();

        window.addEventListener('resize', () => {
            Object.values(this.charts).forEach(chart => {
                if (chart && chart.resize) {
                    chart.resize();
                }
            });
        });
    },
    methods: {
        loadStealthMode() {
            const saved = localStorage.getItem('stealthMode');
            this.stealthMode = saved === 'true';
        },

        toggleStealthMode() {
            this.stealthMode = !this.stealthMode;
            localStorage.setItem('stealthMode', this.stealthMode);
            this.reloadAllCharts();
        },

        async reloadAllCharts() {
            Object.values(this.charts).forEach(chart => {
                if (chart && chart.dispose) {
                    chart.dispose();
                }
            });
            this.charts = {};
            await this.initCharts();
        },

        async loadAllData() {
            this.loading = true;
            try {
                await this.loadOverview();
            } catch (error) {
                console.error('Error loading overview:', error);
                this.loading = false;
                alert('无法加载统计数据，请确保后端服务正在运行');
                return;
            }

            this.loading = false;
            await this.$nextTick();
            await this.initCharts();
        },

        async loadOverview() {
            const response = await axios.get(`${this.apiBaseUrl}/stats/overview`);
            this.overview = response.data.data;
        },

        formatPercent(value) {
            return `${Number(value || 0).toFixed(1)}%`;
        },

        closeDetailModal() {
            this.detailModal.visible = false;
        },

        async openMasteryWords(level, label, count) {
            // 先打开弹窗并展示 loading，再异步请求具体单词，避免用户点击后没有反馈。
            this.detailModal = {
                visible: true,
                loading: true,
                title: label,
                subtitle: `${count || 0} 个单词`,
                type: 'mastery',
                items: []
            };

            try {
                const response = await axios.get(`${this.apiBaseUrl}/stats/mastery-words`, {
                    params: { level, limit: 500 }
                });
                this.detailModal.items = response.data.data || [];
            } finally {
                this.detailModal.loading = false;
            }
        },

        async openErrorTypeWords(errorType, label, count) {
            // 错误类型详情展示的是“最近一次错误输入”和错误次数，便于直接定位问题。
            this.detailModal = {
                visible: true,
                loading: true,
                title: label,
                subtitle: `${count || 0} 次错误`,
                type: 'error',
                items: []
            };

            try {
                const response = await axios.get(`${this.apiBaseUrl}/stats/error-type-words`, {
                    params: { type: errorType, limit: 500 }
                });
                this.detailModal.items = response.data.data || [];
            } finally {
                this.detailModal.loading = false;
            }
        },

        async initCharts() {
            const chartLoaders = [
                ['heatmap', () => this.loadHeatmap()],
                ['accuracy-trend', () => this.loadAccuracyTrend()],
                ['mastery-pie', () => this.loadMasteryPie()],
                ['daily-duration', () => this.loadDailyDuration()],
                ['error-types', () => this.loadErrorTypes()]
            ];

            const results = await Promise.allSettled(chartLoaders.map(([, load]) => load()));
            results.forEach((result, index) => {
                if (result.status === 'rejected') {
                    console.warn(`Failed to load stats chart: ${chartLoaders[index][0]}`, result.reason);
                }
            });
        },

        async loadHeatmap() {
            const chart = echarts.init(document.getElementById('heatmap'));

            const response = await axios.get(`${this.apiBaseUrl}/stats/heatmap`, {
                params: {
                    start_date: '2026-01-01',
                    end_date: '2026-12-31'
                }
            });

            const data = (response.data.data || []).map(item => [item.date, item.count, item.accuracy || 0]);
            this.renderHeatmap(chart, data);
        },

        renderHeatmap(chart, data) {
            const option = {
                title: {
                    text: this.stealthMode ? 'Practice Heatmap' : '学习热力图',
                    left: 'center',
                    textStyle: {
                        color: this.stealthMode ? '#374151' : '#4338ca'
                    }
                },
                tooltip: {
                    formatter: function(params) {
                        const accuracy = Number(params.value[2] || 0).toFixed(1);
                        return `${params.value[0]}<br/>练习次数: ${params.value[1]}<br/>正确率: ${accuracy}%`;
                    }
                },
                visualMap: {
                    min: 0,
                    max: 5,
                    calculable: true,
                    orient: 'horizontal',
                    left: 'center',
                    bottom: '5%',
                    inRange: {
                        color: this.stealthMode
                            ? ['#f3f4f6', '#d1d5db', '#9ca3af', '#6b7280', '#4b5563']
                            : ['#ebedf0', '#c6e48b', '#7bc96f', '#239a3b', '#196127']
                    }
                },
                calendar: {
                    range: '2026',
                    cellSize: ['auto', 13],
                    yearLabel: { show: false }
                },
                series: [{
                    type: 'heatmap',
                    coordinateSystem: 'calendar',
                    data: data
                }]
            };

            chart.setOption(option);
            this.charts.heatmap = chart;
        },

        async loadAccuracyTrend() {
            const chart = echarts.init(document.getElementById('accuracy-trend'));

            const response = await axios.get(`${this.apiBaseUrl}/stats/accuracy-trend`, {
                params: { days: 30 }
            });

            const data = response.data.data || [];
            const dates = data.map(item => item.date);
            const accuracies = data.map(item => item.accuracy);
            const totals = data.map(item => item.total_words);
            this.renderAccuracyTrend(chart, dates, accuracies, totals);
        },

        renderAccuracyTrend(chart, dates, accuracies, totals) {
            const option = {
                title: {
                    text: this.stealthMode ? 'Accuracy Trend' : '正确率趋势',
                    left: 'center',
                    textStyle: {
                        color: this.stealthMode ? '#374151' : '#4338ca'
                    }
                },
                tooltip: {
                    trigger: 'axis',
                    formatter: (params) => {
                        const index = params[0].dataIndex;
                        const accuracy = Number(params[0].value || 0).toFixed(1);
                        return `${params[0].axisValue}<br/>正确率: ${accuracy}%<br/>练习单词: ${totals[index] || 0}`;
                    }
                },
                xAxis: {
                    type: 'category',
                    data: dates,
                    axisLabel: {
                        rotate: 45,
                        interval: Math.floor(dates.length / 10)
                    }
                },
                yAxis: {
                    type: 'value',
                    min: 0,
                    max: 100,
                    axisLabel: { formatter: '{value}%' }
                },
                series: [{
                    name: '正确率',
                    type: 'line',
                    data: accuracies,
                    smooth: true,
                    itemStyle: {
                        color: this.stealthMode ? '#6b7280' : '#5470c6'
                    },
                    areaStyle: {
                        opacity: 0.3
                    }
                }]
            };

            chart.setOption(option);
            this.charts.accuracyTrend = chart;
        },

        async loadMasteryPie() {
            const chart = echarts.init(document.getElementById('mastery-pie'));

            const response = await axios.get(`${this.apiBaseUrl}/stats/mastery-distribution`);
            const data = response.data.data || { mastered: 0, familiar: 0, learning: 0, weak: 0, new: 0 };
            this.renderMasteryPie(chart, data);
        },

        renderMasteryPie(chart, data) {
            // level 字段不参与 ECharts 展示，但点击扇区时会用它请求后端明细接口。
            const pieData = [
                {
                    value: data.mastered,
                    name: this.stealthMode ? 'Mastered' : '已掌握',
                    level: 'mastered',
                    itemStyle: { color: this.stealthMode ? '#6b7280' : '#67C23A' }
                },
                {
                    value: data.familiar,
                    name: this.stealthMode ? 'Familiar' : '熟悉',
                    level: 'familiar',
                    itemStyle: { color: this.stealthMode ? '#9ca3af' : '#409EFF' }
                },
                {
                    value: data.learning,
                    name: this.stealthMode ? 'Learning' : '学习中',
                    level: 'learning',
                    itemStyle: { color: this.stealthMode ? '#d1d5db' : '#E6A23C' }
                },
                {
                    value: data.weak,
                    name: this.stealthMode ? 'Weak' : '薄弱',
                    level: 'weak',
                    itemStyle: { color: this.stealthMode ? '#4b5563' : '#F56C6C' }
                },
                {
                    value: data.new,
                    name: this.stealthMode ? 'New' : '未学习',
                    level: 'new',
                    itemStyle: { color: this.stealthMode ? '#e5e7eb' : '#909399' }
                }
            ];

            const option = {
                title: {
                    text: this.stealthMode ? 'Word Mastery Distribution' : '单词掌握度分布',
                    left: 'center',
                    textStyle: {
                        color: this.stealthMode ? '#374151' : '#4338ca'
                    }
                },
                tooltip: {
                    trigger: 'item',
                    formatter: '{b}: {c} ({d}%)'
                },
                legend: {
                    orient: 'vertical',
                    left: 'left',
                    top: 'middle'
                },
                series: [{
                    type: 'pie',
                    radius: '60%',
                    data: pieData,
                    emphasis: {
                        itemStyle: {
                            shadowBlur: 10,
                            shadowOffsetX: 0,
                            shadowColor: 'rgba(0, 0, 0, 0.5)'
                        }
                    }
                }]
            };

            chart.setOption(option);
            // 切换摸鱼模式会重新渲染图表，先解绑旧 click，避免重复打开弹窗。
            chart.off('click');
            chart.on('click', (params) => {
                if (params.data && params.data.level) {
                    this.openMasteryWords(params.data.level, params.data.name, params.data.value);
                }
            });
            this.charts.masteryPie = chart;
        },

        async loadDailyDuration() {
            const chart = echarts.init(document.getElementById('daily-duration'));

            const response = await axios.get(`${this.apiBaseUrl}/stats/daily-duration`, {
                params: { days: 30 }
            });

            const data = response.data.data || [];
            const dates = data.map(item => item.date);
            const durations = data.map(item => item.duration_minutes);
            const sessions = data.map(item => item.session_count);
            this.renderDailyDuration(chart, dates, durations, sessions);
        },

        renderDailyDuration(chart, dates, durations, sessions) {
            const option = {
                title: {
                    text: this.stealthMode ? 'Daily Practice Duration' : '每日练习时长',
                    left: 'center',
                    textStyle: {
                        color: this.stealthMode ? '#374151' : '#4338ca'
                    }
                },
                tooltip: {
                    trigger: 'axis',
                    formatter: (params) => {
                        const index = params[0].dataIndex;
                        const minutes = Number(params[0].value || 0).toFixed(1);
                        return `${params[0].axisValue}<br/>时长: ${minutes} 分钟<br/>练习次数: ${sessions[index] || 0}`;
                    }
                },
                xAxis: {
                    type: 'category',
                    data: dates,
                    axisLabel: {
                        rotate: 45,
                        interval: Math.floor(dates.length / 10)
                    }
                },
                yAxis: {
                    type: 'value',
                    axisLabel: { formatter: '{value} min' }
                },
                series: [{
                    name: this.stealthMode ? 'Duration' : '时长',
                    type: 'bar',
                    data: durations,
                    itemStyle: {
                        color: this.stealthMode ? '#6b7280' : '#E6A23C'
                    }
                }]
            };

            chart.setOption(option);
            this.charts.dailyDuration = chart;
        },

        async loadErrorTypes() {
            const chart = echarts.init(document.getElementById('error-types'));

            const response = await axios.get(`${this.apiBaseUrl}/stats/error-types`);
            const data = response.data.data || {};
            this.renderErrorTypes(chart, data);
        },

        renderErrorTypes(chart, data) {
            // errorType 字段保留后端枚举值，点击饼图时按枚举值查询具体错误单词。
            const pieData = [
                {
                    value: data.spelling || 0,
                    name: this.stealthMode ? 'Typo' : '拼写错误',
                    errorType: 'spelling',
                    itemStyle: { color: this.stealthMode ? '#6b7280' : '#F56C6C' }
                },
                {
                    value: data.missing_letter,
                    name: this.stealthMode ? 'Missing Letter' : '漏字母',
                    errorType: 'missing_letter',
                    itemStyle: { color: this.stealthMode ? '#9ca3af' : '#E6A23C' }
                },
                {
                    value: data.extra_letter,
                    name: this.stealthMode ? 'Extra Letter' : '多字母',
                    errorType: 'extra_letter',
                    itemStyle: { color: this.stealthMode ? '#d1d5db' : '#409EFF' }
                },
                {
                    value: data.completely_wrong || 0,
                    name: this.stealthMode ? 'Completely Wrong' : '完全错误',
                    errorType: 'completely_wrong',
                    itemStyle: { color: this.stealthMode ? '#4b5563' : '#909399' }
                },
                {
                    value: data.skipped || 0,
                    name: this.stealthMode ? 'Skipped' : '跳过',
                    errorType: 'skipped',
                    itemStyle: { color: this.stealthMode ? '#e5e7eb' : '#67C23A' }
                }
            ];

            const option = {
                title: {
                    text: this.stealthMode ? 'Error Type Distribution' : '错误类型分布',
                    left: 'center',
                    textStyle: {
                        color: this.stealthMode ? '#374151' : '#4338ca'
                    }
                },
                tooltip: {
                    trigger: 'item',
                    formatter: '{b}: {c} ({d}%)'
                },
                legend: {
                    orient: 'vertical',
                    left: 'left',
                    top: 'middle'
                },
                series: [{
                    type: 'pie',
                    radius: ['40%', '70%'],
                    avoidLabelOverlap: false,
                    data: pieData,
                    emphasis: {
                        itemStyle: {
                            shadowBlur: 10,
                            shadowOffsetX: 0,
                            shadowColor: 'rgba(0, 0, 0, 0.5)'
                        }
                    }
                }]
            };

            chart.setOption(option);
            // 与掌握度图一致，重新渲染前清理旧监听器，保持每次点击只发起一次请求。
            chart.off('click');
            chart.on('click', (params) => {
                if (params.data && params.data.errorType) {
                    this.openErrorTypeWords(params.data.errorType, params.data.name, params.data.value);
                }
            });
            this.charts.errorTypes = chart;
        }
    }
}).mount('#app');

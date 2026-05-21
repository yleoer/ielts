// API Client for IELTS Typing Practice

const API_BASE_URL = 'http://localhost:8080/api';

class ApiClient {
    constructor(baseUrl = API_BASE_URL) {
        this.baseUrl = baseUrl;
        this.axios = axios.create({
            baseURL: baseUrl,
            timeout: 10000,
            headers: {
                'Content-Type': 'application/json'
            }
        });

        // Request interceptor
        this.axios.interceptors.request.use(
            config => {
                console.log(`[API] ${config.method.toUpperCase()} ${config.url}`);
                return config;
            },
            error => {
                console.error('[API] Request error:', error);
                return Promise.reject(error);
            }
        );

        // Response interceptor
        this.axios.interceptors.response.use(
            response => {
                console.log(`[API] Response:`, response.data);
                return response;
            },
            error => {
                console.error('[API] Response error:', error);
                return Promise.reject(error);
            }
        );
    }

    /**
     * Get practice words from Anki database
     * @param {number} limit - Number of words to fetch
     * @param {string} category - Word category filter
     * @returns {Promise<Object>}
     */
    async getWords(limit = 20, category = 'all') {
        try {
            const response = await this.axios.get('/words', {
                params: { limit, category }
            });
            return response.data;
        } catch (error) {
            throw new Error(`Failed to fetch words: ${error.message}`);
        }
    }

    /**
     * Check spelling correctness
     * @param {number} wordId - Word ID
     * @param {string} userInput - User's input
     * @returns {Promise<Object>}
     */
    async checkSpelling(wordId, userInput) {
        try {
            const response = await this.axios.post('/check', {
                word_id: wordId,
                user_input: userInput
            });
            return response.data;
        } catch (error) {
            throw new Error(`Failed to check spelling: ${error.message}`);
        }
    }

    /**
     * Submit practice statistics
     * @param {Object} stats - Practice statistics
     * @returns {Promise<Object>}
     */
    async submitStats(stats) {
        try {
            const response = await this.axios.post('/stats', stats);
            return response.data;
        } catch (error) {
            throw new Error(`Failed to submit stats: ${error.message}`);
        }
    }

    /**
     * Get Anki configuration
     * @returns {Promise<Object>}
     */
    async getConfig() {
        try {
            const response = await this.axios.get('/config');
            return response.data;
        } catch (error) {
            throw new Error(`Failed to get config: ${error.message}`);
        }
    }
}

// Export for use in app.js
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ApiClient;
}

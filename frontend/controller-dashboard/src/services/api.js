import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';
const api = axios.create({ baseURL: API_BASE_URL, timeout: 10000 });

export const getTrainETA = async (trainNumber, options = {}) => (await api.get(`/eta/${trainNumber}`, options)).data;
export const getCorridorStatus = async (corridorName = 'MAS-SBC', options = {}) => (await api.get(`/corridor/${corridorName}`, options)).data;
export const healthCheck = async () => (await api.get('/health')).data;
export default api;

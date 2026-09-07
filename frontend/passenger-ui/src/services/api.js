import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';
const api = axios.create({ baseURL: API_BASE_URL, timeout: 10000, headers: { 'Content-Type': 'application/json' } });

export const getTrainETA = async (trainNumber) => (await api.get(`/eta/${encodeURIComponent(trainNumber)}`)).data;
export const getCorridorStatus = async (corridorName = 'MAS-SBC') => (await api.get(`/corridor/${encodeURIComponent(corridorName)}`)).data;
export const getStationDepartures = async (stationCode, limit = 10) => (await api.get(`/stations/${encodeURIComponent(stationCode)}/departures`, { params: { limit } })).data;
export const healthCheck = async () => (await api.get('/health')).data;
export default api;

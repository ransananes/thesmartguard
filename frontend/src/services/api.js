const API_BASE_URL = 'http://localhost:5000/api';

export const api = {
    login: async (username, password) => {
        const response = await fetch(`${API_BASE_URL}/login`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ username, password }),
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.message || 'Login failed');
        }
        return data; // Returns { success: true, token: '...', user: {...} }
    },

    fetchCameras: async () => {
        const token = localStorage.getItem('token');
        const headers = {};
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }

        const response = await fetch(`${API_BASE_URL}/cameras`, {
            headers: headers
        });
        
        if (!response.ok) {
            if (response.status === 401) {
                // Token expired or invalid
                localStorage.removeItem('token');
                localStorage.removeItem('user');
                window.location.href = '/login'; // Simple redirect
            }
            throw new Error('Failed to fetch cameras');
        }
        return response.json();
    },

    addCamera: async (cameraData) => {
        const token = localStorage.getItem('token');
        const headers = {
            'Content-Type': 'application/json',
        };
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }

        const response = await fetch(`${API_BASE_URL}/cameras`, {
            method: 'POST',
            headers: headers,
            body: JSON.stringify(cameraData)
        });

        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.message || 'Failed to add camera');
        }
        return data; // Returns { success: true, camera: {...} }
    },

    deleteCamera: async (cameraId) => {
        const token = localStorage.getItem('token');
        const headers = {};
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }

        const response = await fetch(`${API_BASE_URL}/cameras/${cameraId}`, {
            method: 'DELETE',
            headers: headers
        });

        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.message || 'Failed to delete camera');
        }
        return data; 
    },

    fetchStats: async () => {
        const token = localStorage.getItem('token');
        const headers = {};
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }

        const response = await fetch(`${API_BASE_URL}/stats`, {
            headers: headers
        });
        
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.message || 'Failed to fetch stats');
        }
        return data; // Returns { success: true, stats: {...} }
    },

    addDetection: async (detectionData) => {
        const token = localStorage.getItem('token');
        const headers = {
            'Content-Type': 'application/json',
        };
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }

        const response = await fetch(`${API_BASE_URL}/detections`, {
            method: 'POST',
            headers: headers,
            body: JSON.stringify(detectionData)
        });

        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.message || 'Failed to add detection');
        }
        return data;
    },

    verifyToken: async () => {
        const token = localStorage.getItem('token');
        if (!token) return false;

        try {
            const response = await fetch(`${API_BASE_URL}/verify`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            return response.ok;
        } catch (error) {
            return false;
        }
    }
};

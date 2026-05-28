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
        return data;
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
                localStorage.removeItem('token');
                localStorage.removeItem('user');
                window.location.href = '/login';
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
        return data;
    },

    updateCamera: async (cameraId, cameraData) => {
        const token = localStorage.getItem('token');
        const headers = { 'Content-Type': 'application/json' };
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }

        const response = await fetch(`${API_BASE_URL}/cameras/${cameraId}`, {
            method: 'PUT',
            headers,
            body: JSON.stringify(cameraData)
        });

        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.message || 'Failed to update camera');
        }
        return data;
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
        return data;
    },

    getSettings: async () => {
        const token = localStorage.getItem('token');
        const headers = {};
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }
        const response = await fetch(`${API_BASE_URL}/settings/notifications`, { headers });
        const data = await response.json();
        if (!response.ok) throw new Error(data.message || 'Failed to fetch settings');
        return data;
    },

    updateSettings: async (settings) => {
        const token = localStorage.getItem('token');
        const headers = { 'Content-Type': 'application/json' };
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }
        const response = await fetch(`${API_BASE_URL}/settings/notifications`, {
            method: 'POST',
            headers,
            body: JSON.stringify(settings)
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.message || 'Failed to update settings');
        return data;
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
    },

    fetchDetectionHistory: async () => {
        const token = localStorage.getItem('token');
        const headers = {};
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }
        const response = await fetch(`${API_BASE_URL}/detections/history`, { headers });
        const data = await response.json();
        if (!response.ok) throw new Error(data.message || 'Failed to fetch history');
        return data;
    },

    getFaces: async () => {
        const token = localStorage.getItem('token');
        const headers = {};
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }
        const response = await fetch(`${API_BASE_URL}/faces`, { headers });
        const data = await response.json();
        if (!response.ok) throw new Error(data.message || 'Failed to fetch faces');
        return data;
    },

    addFace: async (formData) => {
        const token = localStorage.getItem('token');
        const headers = {};
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }

        const response = await fetch(`${API_BASE_URL}/faces`, {
            method: 'POST',
            body: formData,
            headers
        });

        const data = await response.json();
        if (!response.ok) throw new Error(data.message || 'Failed to add face');
        return data;
    },

    deleteFace: async (id) => {
        const token = localStorage.getItem('token');
        const headers = {};
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }
        const response = await fetch(`${API_BASE_URL}/faces/${id}`, {
            method: 'DELETE',
            headers
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.message || 'Failed to delete face');
        return data;
    },

    fetchLiveStatus: async () => {
        const token = localStorage.getItem('token');
        const headers = {};
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }
        const response = await fetch(`${API_BASE_URL}/live_status`, { headers });
        const data = await response.json();
        if (!response.ok) return { person_count: 0, faces: [] };
        return data;
    },

    getRecentDetections: async () => {
        const token = localStorage.getItem('token');
        const headers = {};
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }
        const response = await fetch(`${API_BASE_URL}/detections`, { headers });
        const data = await response.json();
        if (!response.ok) throw new Error(data.message || 'Failed to fetch detections');
        return data;
    },

    clearDetections: async () => {
        const token = localStorage.getItem('token');
        const headers = {};
        if (token) headers['Authorization'] = `Bearer ${token}`;
        const response = await fetch(`${API_BASE_URL}/detections/clear`, {
            method: 'POST',
            headers
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.message || 'Failed to clear detections');
        return data;
    },

    addFaceFromDetection: async (detectionId, name) => {
        const token = localStorage.getItem('token');
        const headers = { 'Content-Type': 'application/json' };
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }
        const response = await fetch(`${API_BASE_URL}/faces/from_detection`, {
            method: 'POST',
            body: JSON.stringify({ detection_id: detectionId, name }),
            headers
        });

        const data = await response.json();
        if (!response.ok) throw new Error(data.message || 'Failed to add face from detection');
        return data;
    },

    robot: {
        getStatus: async () => {
            const token = localStorage.getItem('token');
            const headers = token ? { 'Authorization': `Bearer ${token}` } : {};
            const response = await fetch(`${API_BASE_URL}/robot/status`, { headers });
            return response.json();
        },
        connect: async (port) => {
            const token = localStorage.getItem('token');
            const headers = { 'Content-Type': 'application/json' };
            if (token) headers['Authorization'] = `Bearer ${token}`;
            const response = await fetch(`${API_BASE_URL}/robot/connect`, {
                method: 'POST',
                headers,
                body: JSON.stringify({ port })
            });
            return response.json();
        },
        disconnect: async () => {
            const token = localStorage.getItem('token');
            const headers = token ? { 'Authorization': `Bearer ${token}` } : {};
            const response = await fetch(`${API_BASE_URL}/robot/disconnect`, {
                method: 'POST',
                headers
            });
            return response.json();
        },
        control: async (command) => {
            const token = localStorage.getItem('token');
            const headers = { 'Content-Type': 'application/json' };
            if (token) headers['Authorization'] = `Bearer ${token}`;
            const response = await fetch(`${API_BASE_URL}/robot/control`, {
                method: 'POST',
                headers,
                body: JSON.stringify({ command })
            });
            return response.json();
        },
        toggleFollow: async (enabled, knownOnly = false) => {
            const token = localStorage.getItem('token');
            const headers = { 'Content-Type': 'application/json' };
            if (token) headers['Authorization'] = `Bearer ${token}`;
            const response = await fetch(`${API_BASE_URL}/robot/follow`, {
                method: 'POST',
                headers,
                body: JSON.stringify({ enabled, known_only: knownOnly })
            });
            return response.json();
        },
        toggleFollowUnknowns: async (enabled) => {
            const token = localStorage.getItem('token');
            const headers = { 'Content-Type': 'application/json' };
            if (token) headers['Authorization'] = `Bearer ${token}`;
            const response = await fetch(`${API_BASE_URL}/robot/follow_unknowns`, {
                method: 'POST',
                headers,
                body: JSON.stringify({ enabled })
            });
            return response.json();
        },
        registerHome: async () => {
            const token = localStorage.getItem('token');
            const headers = { 'Content-Type': 'application/json' };
            if (token) headers['Authorization'] = `Bearer ${token}`;
            const response = await fetch(`${API_BASE_URL}/robot/register_home`, {
                method: 'POST',
                headers
            });
            return response.json();
        },
        returnHome: async () => {
            const token = localStorage.getItem('token');
            const headers = { 'Content-Type': 'application/json' };
            if (token) headers['Authorization'] = `Bearer ${token}`;
            const response = await fetch(`${API_BASE_URL}/robot/return_home`, {
                method: 'POST',
                headers
            });
            return response.json();
        }
    }
};

import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import StatusMonitor from './pages/StatusMonitor';
import Login from './pages/Login';
import { api } from './services/api';
import { Toaster } from 'react-hot-toast';

const ProtectedRoute = ({ children, isAuthenticated }) => {
    if (!isAuthenticated) {
        return <Navigate to="/" replace />;
    }
    return children;
};

const PublicRoute = ({ children, isAuthenticated }) => {
    if (isAuthenticated) {
        return <Navigate to="/dashboard" replace />;
    }
    return children;
};

function App() {
    const [isAuthenticated, setIsAuthenticated] = useState(false);
    const [isLoading, setIsLoading] = useState(true);

    useEffect(() => {
        const verifyAuth = async () => {
            const isValid = await api.verifyToken();
            setIsAuthenticated(isValid);
            if (!isValid) {
                localStorage.removeItem('token');
                localStorage.removeItem('user');
                localStorage.removeItem('isAuthenticated');
            }
            setIsLoading(false);
        };
        verifyAuth();
    }, []);

    if (isLoading) {
        return (
            <div className="min-h-screen bg-black flex items-center justify-center text-white">
                <div className="flex flex-col items-center gap-4">
                    <div className="w-8 h-8 border-2 border-purple-500 border-t-transparent rounded-full animate-spin" />
                    <span className="text-sm font-mono text-purple-400">INITIALIZING SECURITY PROTOCOLS...</span>
                </div>
            </div>
        );
    }

    return (
        <Router>
            <Toaster 
                position="top-right" 
                toastOptions={{
                    style: {
                        background: '#333',
                        color: '#fff',
                    },
                }}
            />
            <Routes>
                <Route 
                    path="/" 
                    element={
                        <PublicRoute isAuthenticated={isAuthenticated}>
                            <Login onLogin={() => setIsAuthenticated(true)} />
                        </PublicRoute>
                    } 
                />
                <Route 
                    path="/dashboard" 
                    element={
                        <ProtectedRoute isAuthenticated={isAuthenticated}>
                            <StatusMonitor />
                        </ProtectedRoute>
                    } 
                />
            </Routes>
        </Router>
    );
}

export default App;

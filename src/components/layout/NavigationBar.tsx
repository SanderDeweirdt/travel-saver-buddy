
import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { Home, BookOpen, PlusCircle, User, LayoutDashboard } from 'lucide-react';

const NavigationBar = () => {
  const location = useLocation();
  
  const isActive = (path: string) => location.pathname === path;
  
  const navItems = [
    { 
      icon: <LayoutDashboard size={20} />, 
      label: 'Dashboard', 
      path: '/dashboard',
      active: isActive('/dashboard')
    },
    { 
      icon: <BookOpen size={20} />, 
      label: 'Bookings', 
      path: '/bookings',
      active: isActive('/bookings')
    },
    { 
      icon: <PlusCircle size={20} />, 
      label: 'Add', 
      path: '/add-booking',
      active: isActive('/add-booking')
    },
    { 
      icon: <User size={20} />, 
      label: 'Profile', 
      path: '/profile',
      active: isActive('/profile')
    },
  ];
  
  return (
    <div className="md:hidden fixed bottom-0 left-0 right-0 bg-white/90 backdrop-blur-md border-t border-border z-50 px-2 pb-2 pt-1">
      <div className="max-w-lg mx-auto flex items-center justify-around">
        {navItems.map((item) => (
          <Link
            key={item.path}
            to={item.path}
            className={cn(
              "flex flex-col items-center justify-center py-2 px-2 rounded-xl transition-colors",
              item.active 
                ? "text-primary" 
                : "text-muted-foreground hover:text-foreground"
            )}
          >
            <div className={cn(
              "flex items-center justify-center transition-transform duration-200 mb-1",
              item.active ? "scale-110" : ""
            )}>
              {item.icon}
            </div>
            <span className="text-xs font-medium">{item.label}</span>
            {item.active && (
              <div className="absolute -bottom-1 w-1 h-1 bg-primary rounded-full" />
            )}
          </Link>
        ))}
      </div>
    </div>
  );
};

export default NavigationBar;

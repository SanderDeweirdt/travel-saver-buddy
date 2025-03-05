
import { useAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/button';
import { LogOut, User } from 'lucide-react';

const UserMenu = () => {
  const { user, signOut, loading } = useAuth();

  if (!user) {
    return null;
  }

  return (
    <div className="flex items-center gap-4">
      <div className="flex items-center gap-2">
        <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center">
          <User className="h-4 w-4 text-primary" />
        </div>
        <span className="text-sm font-medium">{user.email}</span>
      </div>
      <Button 
        variant="outline" 
        size="sm" 
        onClick={signOut}
        disabled={loading}
      >
        <LogOut className="h-4 w-4 mr-2" />
        Sign out
      </Button>
    </div>
  );
};

export default UserMenu;

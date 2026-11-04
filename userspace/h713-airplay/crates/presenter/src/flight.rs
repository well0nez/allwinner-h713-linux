// SPDX-License-Identifier: GPL-3.0-only
//! Pictures lent to h713-warp: each committed wl_buffer keeps what it shows (the decoder's frame, its wl_buffer)
//! until the server releases it; only then is the frame given back to the decoder's pool.

pub struct Flight<T> {
    lent: Vec<(u64, T)>,
    next: u64,
}

impl<T> Default for Flight<T> {
    fn default() -> Self {
        Flight { lent: Vec::new(), next: 1 }
    }
}

impl<T> Flight<T> {
    /// A new id for the buffer about to be made; `lend` it once the buffer exists.
    pub fn next_id(&mut self) -> u64 {
        let id = self.next;
        self.next += 1;
        id
    }

    pub fn lend(&mut self, id: u64, item: T) {
        self.lent.push((id, item));
    }

    /// What the released buffer held; `None` for an id that is not lent (a second release).
    pub fn release(&mut self, id: u64) -> Option<T> {
        let at = self.lent.iter().position(|(i, _)| *i == id)?;
        Some(self.lent.swap_remove(at).1)
    }

    pub fn len(&self) -> usize {
        self.lent.len()
    }

    pub fn is_empty(&self) -> bool {
        self.lent.is_empty()
    }

    pub fn drain(&mut self) -> impl Iterator<Item = T> + '_ {
        self.lent.drain(..).map(|(_, t)| t)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::Cell;
    use std::rc::Rc;

    struct Lent(Rc<Cell<u32>>);
    impl Drop for Lent {
        fn drop(&mut self) {
            self.0.set(self.0.get() + 1);
        }
    }

    #[test]
    fn a_frame_goes_back_only_at_its_own_release() {
        let back = Rc::new(Cell::new(0));
        let mut f = Flight::default();
        let (a, b) = (f.next_id(), f.next_id());
        f.lend(a, Lent(back.clone()));
        f.lend(b, Lent(back.clone()));
        assert_eq!(back.get(), 0);
        drop(f.release(b));
        assert_eq!((back.get(), f.len()), (1, 1), "the newer one first: the server releases in any order");
        assert!(f.release(b).is_none(), "a second release returns nothing");
        drop(f.release(a));
        assert_eq!((back.get(), f.is_empty()), (2, true));
    }

    #[test]
    fn the_end_of_the_session_gives_everything_back() {
        let back = Rc::new(Cell::new(0));
        let mut f = Flight::default();
        for _ in 0..3 {
            let id = f.next_id();
            f.lend(id, Lent(back.clone()));
        }
        f.drain().for_each(drop);
        assert_eq!((back.get(), f.len()), (3, 0));
    }
}

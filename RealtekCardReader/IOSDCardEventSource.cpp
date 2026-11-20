//
//  IOSDCardEventSource.cpp
//  RealtekCardReader
//
//  Created by FireWolf on 6/9/21.
//

#include "IOSDCardEventSource.hpp"

#include "Debug.hpp"

//
// MARK: - Meta Class Definitions
//

OSDefineMetaClassAndStructors(IOSDCardEventSource, IOEventSource);

///
/// Check whether an action needs to perform to handle the card event
///
/// @return `false` always. The owner must explictly invoke `IOSDCardEventSource::enable()` to trigger another action.
///
bool IOSDCardEventSource::checkForWork()
{
    IOLockLock(this->eventLock);
    if (!this->enabled)
    {
        IOLockUnlock(this->eventLock);
        return false;
    }

    auto completion = this->completion;
    auto options = this->options;
    this->completion.reset();
    super::disable();
    IOLockUnlock(this->eventLock);

    // A new event may arrive while the host is initializing the card.
    (*reinterpret_cast<Action>(this->action))(this->owner, &completion, options);
    return false;
}

///
/// Enable the event source
///
/// @param completion A nullable completion routine to be invoked when the card event has been processed
/// @param options An optional value passed to the host driver
///
void IOSDCardEventSource::enable(IOSDCard::Completion* completion, IOSDCard::EventOptions options)
{
    IOLockLock(this->eventLock);
    auto displaced = this->completion;
    this->completion = completion != nullptr ? *completion : IOSDCard::Completion{};
    this->options = options;
    super::enable();
    IOLockUnlock(this->eventLock);

    if (displaced.hasAction())
    {
        displaced.invoke(kIOReturnAborted, nullptr);
    }
}

///
/// Disable the event source
///
void IOSDCardEventSource::disable()
{
    IOLockLock(this->eventLock);
    auto cancelled = this->completion;
    this->completion.reset();
    super::disable();
    IOLockUnlock(this->eventLock);

    if (cancelled.hasAction())
    {
        cancelled.invoke(kIOReturnAborted, nullptr);
    }
}

///
/// Create a card event source with the given action
///
/// @param owner Owner of the returned instance; the first parameter of the action routine
/// @param action A non-null action to process the card insertion or removal event
/// @return A non-null event source on success, `nullptr` otherwise.
///
IOSDCardEventSource* IOSDCardEventSource::createWithAction(OSObject* owner, Action action)
{
    if (action == nullptr)
    {
        perr("The action routine must be non-null.");
        
        return nullptr;
    }
    
    auto instance = OSTypeAlloc(IOSDCardEventSource);
    
    if (instance == nullptr)
    {
        return nullptr;
    }
    
    if (!instance->init(owner, reinterpret_cast<IOEventSource::Action>(action)))
    {
        instance->release();
        
        return nullptr;
    }
    
    instance->eventLock = IOLockAlloc();
    if (instance->eventLock == nullptr)
    {
        instance->release();
        return nullptr;
    }

    instance->completion.reset();
    instance->disable();
    return instance;
}


void IOSDCardEventSource::free()
{
    if (this->eventLock != nullptr)
    {
        IOLockFree(this->eventLock);
    }
    super::free();
}
